"""MODULAR BUILDER: assemble a rigged paper character from a recipe of parts.

    B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
    nice -n 10 $B -b -t 2 -P blender/character/modular_builder.py -- \
        --recipe library/character-recipes/ronin-reference.json --out output/character/ronin.blend
    ... -- --recipe <r> --pose chudan --still output/character/ronin.png
    ... -- --recipe <r> --turnaround output/character/ronin-turn.png --light neutral

What it does, in order:
  1. builds the shared humanoid rig: the SAME joint names as engine/figure.js and rig_trellis.py
     (root hips torso upper neck head, rC rS rE rT rH + l…, r/l thigh shin foot, hakama), as empties
     driving a deform armature, so library/poses.json poses it and film_blender.py can drive it;
  2. loads the recipe's parts from blender/character/part_registry.py, snaps each one to its socket in the
     rest pose, scales it INSIDE its approved range (scaling the mesh, never the object, so the washi fibre
     stays world-size on every part), and assigns its sheet from library/paper-materials/;
  3. hides faces that are sealed inside another part of the same bone;
  4. parents rigid parts to their bone and skins flexible ones (sleeves, hakama legs) across 2-3 bones;
  5. poses it and hands back {'rig', 'joints', 'objects', 'collection'}.

Recipe format: see library/character-recipes/ronin-reference.json and docs/CHARACTER-FACTORY.md.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'world'))
import paper_materials as pm            # noqa: E402
import part_registry as reg             # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index('--' + n) + 1] if '--' + n in ARGV else d


def flag(n):
    return '--' + n in ARGV


# =========================================================================== poses (port of engine/figure.js)
POSES = json.load(open(os.path.join(REPO, 'library', 'poses.json')))
BASE = dict(x=0, y=0, z=0, ry=0, rx=0, rz=0, tx=0, ty=0, tz=0, hx=0, hy=0, hz=0, rsx=0.05, rsz=0.12, rex=-0.15,
            lsx=0.05, lsz=-0.12, lex=-0.15, rwx=0, lwx=0, rwz=0, lwz=0, sway=0, swayx=0, stance=0.12, crouch=0,
            weight=0, cx=0, cy=0, cz=0, nx=0, ny=0, rcy=0, rcz=0, lcy=0, lcz=0, rsy=0, lsy=0, rfy=0, lfy=0,
            rax=0, lax=0, px=0, py=0, pz=0, rtx=0, ltx=0)
# engine/figure.js LEG, the same numbers (28 Nov: posed hips and ankles = the rest skeleton, soft IK from 0.99, a toe
# joint at the ball, the heel-raise reach rule, the knee limit). Keep the two in step: legs_match.py proves they are.
LEG = dict(thigh=0.46, shin=0.44, hipY=0.92, hipDrop=0.0, footY=0.02, soft=0.99, toeZ=0.10, toeY=-0.02,
           heelMax=0.6, kneeMax=2.7, hipW=0.1)
POSES.setdefault('standing', {'tx': 0.06, 'hx': 0.22, 'nx': 0.1, 'rsx': -0.55, 'rsz': 0.35, 'rex': -1.4,
                              'lsx': -0.5, 'lsz': -0.4, 'lex': -1.45, 'stance': 0.18})


def T(x, y, z):
    """three.js (figure.js) coordinates → Blender."""
    return Vector((x, -z, y))


def heel_raise(hx, hy, hz, fx, fy, fz, reach, q0=0.0):
    """engine/figure.js heelRaise: the heel-up angle (about the toe joint on the ground) that brings a stance ankle
    within `reach` of the hip, then a slide in along the ground. Returns (q, fx, fy, fz), figure.js axes."""
    tz, ty = LEG['toeZ'], LEG['toeY']

    def at(q):
        return (fy + ty + (-ty) * math.cos(q) + tz * math.sin(q), fz + tz + (-ty) * math.sin(q) - tz * math.cos(q))

    def dist(q):
        y, z = at(q)
        return math.sqrt((fx - hx) ** 2 + (y - hy) ** 2 + (z - hz) ** 2)
    if dist(q0) <= reach:
        y, z = at(q0)
        return q0, fx, y, z
    lo, hi = q0, max(q0, LEG['heelMax'])
    if dist(hi) >= dist(q0):                        # a foot ahead of the hip gains nothing on its toes: slide it in
        y, z = at(q0)
        h = max(0.0, reach * reach - (fx - hx) ** 2 - (y - hy) ** 2)
        return q0, fx, y, hz + math.copysign(math.sqrt(h), z - hz)
    if dist(hi) > reach:
        y, z = at(hi)
        h = max(0.0, reach * reach - (fx - hx) ** 2 - (y - hy) ** 2)
        return hi, fx, y, hz + math.copysign(math.sqrt(h), z - hz)
    for _ in range(24):
        mid = (lo + hi) / 2
        if dist(mid) > reach:
            lo = mid
        else:
            hi = mid
    y, z = at(hi)
    return hi, fx, y, z


# =========================================================================== the shared rig
class Rig:
    """Empties (the exact figure.js kinematics) with a deform armature constrained to them."""

    def __init__(self, coll, name='PC'):
        self.coll = coll
        self.J = {}
        self.name = name
        self._build_joints()
        self._build_armature()

    def _joint(self, n, parent, local_three):
        e = bpy.data.objects.new('J_' + n + '_' + self.name, None)
        e.empty_display_size = 0.04
        e.rotation_mode = 'YZX'
        self.coll.objects.link(e)
        if parent:
            e.parent = self.J[parent]
        e.location = T(*local_three)
        self.J[n] = e
        # figure.js turn orders: every joint is three.js 'XYZ' (Blender 'YZX' with rot()'s axis swap), but the ROOT
        # is 'YXZ' (facing first, then the lean: a forward lean leans forward whatever way the body faces) and the
        # THIGHS are 'ZXY' (bend in the leg plane, then roll the plane: hip abduction). Until 28 Nov all were 'YZX':
        # a lean on a body facing 2.3 rad came out mostly sideways; a rolled leg plane bent the wrong way.
        if n in ('root', 'hips'):                         # the pelvis turns first too (figure.js hips: 'YXZ')
            e.rotation_mode = 'YXZ'
        elif n.endswith('thigh'):
            e.rotation_mode = 'XYZ'
        return e

    def _build_joints(self):
        self._joint('root', None, (0, 0, 0))
        self._joint('hips', 'root', (0, 0.92, 0))
        self._joint('torso', 'hips', (0, 0, 0))
        self._joint('upper', 'torso', (0, 0.26, 0))
        self._joint('neck', 'upper', (0, 0.29, 0))
        self._joint('head', 'neck', (0, 0.06, 0))
        self._joint('hakama', 'hips', (0, 0, 0))
        for s, sgn in (('r', -1), ('l', 1)):
            self._joint(s + 'C', 'upper', (sgn * 0.07, 0.21, 0))
            self._joint(s + 'S', s + 'C', (sgn * 0.16, 0, 0))
            self._joint(s + 'E', s + 'S', (0, -0.30, 0))
            self._joint(s + 'T', s + 'E', (0, 0, 0))
            self._joint(s + 'H', s + 'T', (0, -0.29, 0))
            # SLEEVE BONE. The tamoto is cloth, not part of the arm: it hangs from the forearm but
            # keeps falling toward the ground when the arm lifts, instead of swinging over the head
            # with it. It needs a joint of its own for that; _hang_sleeves() aims it every frame.
            # Same place as engine/figure.js hangs its tamoto group (tamoto.position.y = -0.1).
            self._joint(s + 'Sleeve', s + 'T', (0, -0.10, 0))
            self._joint(s + 'thigh', 'root', (sgn * 0.1, 0.92, 0))
            self._joint(s + 'shin', s + 'thigh', (0, -0.46, 0))
            self._joint(s + 'foot', s + 'shin', (0, -0.44, 0))
            self._joint(s + 'toe', s + 'foot', (0, LEG['toeY'], LEG['toeZ']))
        bpy.context.view_layer.update()

    def _build_armature(self):
        """One deform bone per joint, each constrained to its empty: rigid parts parent, soft parts skin."""
        arm = bpy.data.armatures.new('ARM_' + self.name)
        rig = bpy.data.objects.new('RIG_' + self.name, arm)
        self.coll.objects.link(rig)
        self.rig = rig
        prev = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        kids = {}
        for b, p in reg.PARENT.items():
            kids.setdefault(p, []).append(b)
        for b, head in reg.REST.items():
            eb = arm.edit_bones.new(b)
            eb.head = Vector(head)
            ch = [k for k in kids.get(b, []) if Vector(reg.REST[k]) != Vector(head)]
            if b in getattr(reg, 'TAIL', {}):
                eb.tail = Vector(reg.TAIL[b])
            else:
                eb.tail = Vector(reg.REST[ch[0]]) if ch else Vector(head) + Vector((0, 0, 0.09))
            if (eb.tail - eb.head).length < 1e-4:
                eb.tail = eb.head + Vector((0, 0, 0.09))
        for b, p in reg.PARENT.items():
            arm.edit_bones[b].parent = arm.edit_bones[p]
            arm.edit_bones[b].use_connect = False
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = prev
        self.rest_bone = {b: arm.bones[b].matrix_local.copy() for b in reg.REST}
        # Bone order parent-first: setting pose_bone.matrix reads the parent's current pose.
        self.order = []
        todo = [b for b in reg.REST if b not in reg.PARENT]
        while todo:
            b = todo.pop(0)
            self.order.append(b)
            todo += [k for k, p in reg.PARENT.items() if p == b]
        bpy.context.view_layer.update()

    def sync_bones(self):
        """Drive the deform bones from the empties.

        A bone's rest orientation has nothing to do with its empty's (bones point along their own Y), so a
        Copy Transforms constraint would shear every skinned part. What a skin wants is the empty's DELTA
        from rest applied to the bone's own rest matrix: D = empty_now @ empty_rest^-1 (the empties are pure
        translations at rest, so empty_rest is just Translation(REST[b]))."""
        for b in self.order:
            D = self.J[b].matrix_world @ Matrix.Translation(-Vector(reg.REST[b]))
            self.rig.pose.bones[b].matrix = D @ self.rest_bone[b]
            bpy.context.view_layer.update()

    def key_bones(self, frame):
        """BAKE the deform bones on this frame (call after pose()/sync_bones()).

        sync_bones() writes the bones directly; nothing keys them and nothing ties them to the control
        empties, so on any later frame change the skinned paper (kimono, hakama, sleeves) stayed in the LAST
        synced pose while the rigid parts moved with the keyed empties (proved 26 Nov: dash-test frames 10
        and 150, rigid parts 5.3 m apart, skinned parts identical). Keying every bone makes the evaluated
        armature the source of truth: any frame, any order, any fresh render process."""
        for pb in self.rig.pose.bones:
            pb.rotation_mode = 'QUATERNION'
            pb.keyframe_insert('location', frame=frame, group=pb.name)
            pb.keyframe_insert('rotation_quaternion', frame=frame, group=pb.name)
            pb.keyframe_insert('scale', frame=frame, group=pb.name)

    # ---- the pose solver, ported from engine/figure.js applyPose + solveLegs
    def rot(self, j, rx, ry, rz):
        self.J[j].rotation_euler = (rx, -rz, ry)

    def pose(self, name='standing', **over):
        p = dict(BASE)
        p.update(POSES.get(name, {}) if isinstance(name, str) else (name or {}))
        p.update(over)
        J = self.J
        J['root'].location = T(p['x'], p['y'], p['z'])
        self.rot('root', p['rx'], p['ry'], p['rz'])
        hipY = LEG['hipY'] - p['crouch']
        hipZ = p['weight'] * p['stance'] * 0.35
        J['hips'].location = T(0, hipY, hipZ)
        self.rot('hips', p.get('px', 0.0), p.get('py', 0.0), p.get('pz', 0.0))
        self.rot('torso', p['tx'] + p['weight'] * 0.05, p['ty'], p['tz'])
        self.rot('upper', p['cx'], p['cy'], p['cz'])
        self.rot('neck', p['nx'], p['ny'], 0)
        self.rot('head', p['hx'], p['hy'], p['hz'])
        self.rot('rC', 0, p['rcy'], -p['rcz']); self.rot('lC', 0, -p['lcy'], p['lcz'])
        self.rot('rS', p['rsx'], p['rsy'], p['rsz']); self.rot('lS', p['lsx'], p['lsy'], p['lsz'])
        self.rot('rE', p['rex'], 0, 0); self.rot('lE', p['lex'], 0, 0)
        self.rot('rT', 0, p['rfy'], 0); self.rot('lT', 0, p['lfy'], 0)
        self.rot('rH', p['rwx'], 0, p['rwz']); self.rot('lH', p['lwx'], 0, p['lwz'])
        self.rot('hakama', p['swayx'], 0, p['sway'])
        self._solve_legs(p, hipY - LEG['hipDrop'], hipZ)
        bpy.context.view_layer.update()
        self._hang_sleeves(p)
        bpy.context.view_layer.update()
        self.sync_bones()
        return p

    def _solve_legs(self, p, hy, hzz):
        """The port of engine/figure.js solveLegs, the same numbers. Without `_feet` each foot is placed from the
        stance (and stride/phase) in the figure's own frame. With `_feet` (engine/footlock.js: the timeline carries
        it in every pose of a film with motion.lockFeet) each foot is a WORLD point (three.js coordinates) brought
        into the root's frame: the foot stays planted and the hips move over it. Until 28 Nov this port ignored
        `_feet`, so every render placed the feet from the stance: in Episode 1 the 'planted' left foot glided 0.66 m
        in 28 frames at 4 cm height while the plan held it still, and the hips sank for steps that never happened.
        Soft IK and the stretch that pays its shortfall back, the leg plane rolled sideways to contain the hip-foot
        line, and the foot's pitch (`_feet.pr` / `.pl`, + toe up: heel strike and toe-off) as in figure.js."""
        J = self.J
        L1, L2 = LEG['thigh'], LEG['shin']
        feet = p.get('_feet')
        inv = None
        if feet:
            root = J['root']
            if root.parent is None:                        # its world matrix is its own transform: no scene update
                inv = root.matrix_basis.inverted()
            else:
                bpy.context.view_layer.update()
                inv = root.matrix_world.inverted()
        px, py, pz = p.get('px', 0.0) or 0.0, p.get('py', 0.0) or 0.0, p.get('pz', 0.0) or 0.0
        pel = (px, py, pz) != (0.0, 0.0, 0.0)
        for s, side in (('r', -1), ('l', 1)):
            front = side < 0
            hx, hy_, hz_ = side * LEG['hipW'], hy, hzz
            if pel:                                        # the pelvis carries the hip joint (three.js YXZ = Blender YXZ)
                o = Euler((px, -pz, py), 'YXZ').to_matrix() @ T(side * LEG['hipW'], 0, 0)
                hx, hy_, hz_ = o.x, hy + o.z, hzz - o.y
            fx, fy, fz = side * 0.1, LEG['footY'], (1 if front else -1) * p['stance'] / 2
            pitch, heel = 0.0, 0.0
            if feet:
                w = feet['r' if front else 'l']
                v = inv @ T(w[0], w[1], w[2])              # the root's frame, Blender axes
                fx, fy, fz = v.x, v.z, -v.y                # ... back to figure.js axes
                pitch = float(feet.get('p' + ('r' if front else 'l'), 0.0) or 0.0)
            elif p.get('stride', 0) > 0:                   # walking feet of a motion capture (figure.js)
                ph = p.get('phase', 0.0) + (0.0 if front else math.pi)
                fz += math.sin(ph) * p['stride'] / 2
                fy += max(0.0, math.cos(ph)) * 0.07
            ank = p['rax'] if front else p['lax']
            q0 = max(0.0, ank)                             # an ankle pointed down on the ground: a heel raised on the ball
            if not feet and fy <= LEG['footY'] + 1e-6:     # a foot on the ground: past the reach, onto its toes
                heel, fx, fy, fz = heel_raise(hx, hy_, hz_, fx, fy, fz, (L1 + L2) * 1.012, q0)
            sx, sy = fx - hx, fy - hy_
            roll = math.atan2(sx, -sy) + (0.0 if feet else side * 0.04)   # the splay: a stance foot only
            dz, dy = fz - hz_, -math.hypot(sx, sy)
            d = math.hypot(dz, dy)
            true_d = d
            mx = (L1 + L2) * 0.999
            ds = (L1 + L2) * (float(feet.get('soft', LEG['soft']) or LEG['soft']) if feet else LEG['soft'])
            if d > ds:                                     # soft IK: eases onto mx
                room = mx - ds
                soft = mx - room * math.exp(-(d - ds) / room)
                if d > 1e-6:
                    dz *= soft / d
                    dy *= soft / d
                d = soft
            dmin = math.sqrt(L1 * L1 + L2 * L2 + 2 * L1 * L2 * math.cos(LEG['kneeMax']))   # the knee limit
            if 1e-6 < d < dmin:
                dz *= dmin / d
                dy *= dmin / d
                d = dmin
            phi = math.atan2(dz, -dy)
            a = math.acos(max(-1, min(1, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * max(d, 1e-6)))))
            th = phi + a
            kz, ky = hz_ + L1 * math.sin(th), hy_ - L1 * math.cos(th)
            sh = math.atan2(hz_ + dz - kz, -(hy_ + dy - ky))
            J[s + 'thigh'].location = T(hx, hy_, hz_)
            self.rot(s + 'thigh', -th, 0, roll)            # Euler XYZ here = figure.js's ZXY (bend, then roll)
            J[s + 'thigh'].scale = (1.0,) * 3 if d < 1e-6 else (max(1.0, true_d / d),) * 3
            self.rot(s + 'shin', -(sh - th), 0, 0)
            twist = 0.0                                    # the planted foot's own direction (figure.js: yr / yl)
            if feet and feet.get('y' + ('r' if front else 'l')) is not None:
                d_ = float(feet['y' + ('r' if front else 'l')]) - p['ry']
                tw = float(feet.get('twist', 1.05) or 1.05)
                twist = max(-tw, min(tw, math.atan2(math.sin(d_), math.cos(d_))))
            self.rot(s + 'foot', sh + ank - pitch + (heel - q0 if heel > 0 else 0.0), twist, 0)
            # the toe stays flat while the heel is up (the reach rule's heel, or a foot plan pivoting on the ball)
            ball_up = max(0.0, -pitch) if (feet and feet.get('ball')) else 0.0
            self.rot(s + 'toe', -(heel + ball_up) - (p.get('rtx', 0.0) if front else p.get('ltx', 0.0)), 0, 0)

    def ground_feet(self, ground=0.0, rest=LEG['footY'], tol=0.004, base=0.0):
        """After pose(): an ankle under the world ground is put back ON it by re-solving that leg - the hip swing
        and the knee - with the hip where the pose left it, the ankle at the same place across the ground, and the
        foot turned back so the sole keeps its angle. pose() solves the legs in the character's own frame, so a
        lean or a drop of the whole body carried a foot into the sand (27 Nov: Kojiro's right foot 8.3 cm deep for
        6 frames of the lunge; tools/bake_events.py reports these as 'sink'). Returns {side: cm lifted}."""
        J, out = self.J, {}
        self.foot_ground = {}                               # the ground used under each foot (the bake records it)
        for s in ('r', 'l'):
            foot, th, sh = J[s + 'foot'], J[s + 'thigh'], J[s + 'shin']
            a0 = foot.matrix_world.translation.copy()
            gz = ground(a0.x, a0.y, a0.z + 0.4) if callable(ground) else ground
            if gz is None:
                gz = base
            self.foot_ground[s] = round(float(gz), 4)
            want = gz + rest
            planted = a0.z <= base + rest + 0.02            # on its own ground in the pose (base: the ground it was posed on)
            if a0.z >= want - tol and not (planted and a0.z > want + tol):
                continue                                    # on or above its ground, or a raised foot over a dip
            hip = th.matrix_world.translation.copy()
            flat = Vector((a0.x - hip.x, a0.y - hip.y, 0.0))
            fwd = flat.normalized() if flat.length > 1e-4 else Vector((0.0, -1.0, 0.0))
            goal = Vector((a0.x, a0.y, want))

            def resid():
                bpy.context.view_layer.update()
                a = foot.matrix_world.translation
                return Vector(((a.z - goal.z), (a - goal).dot(fwd)))
            x0 = Vector((th.rotation_euler[0], sh.rotation_euler[0]))
            x = x0.copy()
            for _ in range(8):
                th.rotation_euler[0], sh.rotation_euler[0] = x
                r = resid()
                if r.length < 0.002:
                    break
                cols = []
                for k in range(2):
                    xe = x.copy()
                    xe[k] += 1e-3
                    th.rotation_euler[0], sh.rotation_euler[0] = xe
                    cols.append((resid() - r) / 1e-3)
                a11, a21, a12, a22 = cols[0][0], cols[0][1], cols[1][0], cols[1][1]
                det = a11 * a22 - a12 * a21
                if abs(det) < 1e-9:
                    break
                dx = Vector(((a22 * r[0] - a12 * r[1]) / det, (-a21 * r[0] + a11 * r[1]) / det))
                if dx.length > 0.35:
                    dx *= 0.35 / dx.length
                x -= dx
            th.rotation_euler[0], sh.rotation_euler[0] = x
            foot.rotation_euler[0] -= (x[0] - x0[0]) + (x[1] - x0[1])
            bpy.context.view_layer.update()
            out[s] = round((foot.matrix_world.translation.z - a0.z) * 100, 1)
        if out:
            self.sync_bones()
        return out

    def _hang_sleeves(self, p):
        """Aim each sleeve bone at the ground, pushed outward as the arm rises.

        This is the port of engine/figure.js hangCloth(). A sleeve skinned to the arm alone follows
        the arm rigidly, so an overhead cut swings the tamoto over the head and the face disappears
        into its own cloth. Real fabric does not do that: it keeps hanging down, and what the lifted
        arm does is pull it OUT to the side, away from the head.

        `raise` is how far the forearm points up, read off the forearm's own axis (down-the-limb is
        the joint's local -Z here, because T() maps three.js (0,-1,0) to Blender (0,0,-1)): 0 with the
        arm hanging, 1 with it overhead. The outward push scales with it, and the small blend back
        toward the forearm - which is what tips the hem over the face - fades out as the arm lifts."""
        sway = p.get('sway', 0.0)
        rootq = self.J['root'].matrix_world.to_quaternion()
        down = Vector((0.0, 0.0, -1.0))
        for s, lat in (('r', -1.0), ('l', 1.0)):
            e = self.J[s + 'Sleeve']
            e.rotation_euler = (0.0, 0.0, 0.0)
            bpy.context.view_layer.update()
            pq = e.parent.matrix_world.to_quaternion()
            up = (pq @ down).z                              # +1 forearm overhead, -1 hanging
            rise = max(0.0, min(1.0, up))
            d = rootq @ Vector((sway * 0.4 + 2.2 * rise * lat, 0.0, -1.0))
            q = down.rotation_difference((pq.inverted() @ d).normalized())
            e.rotation_euler = q.slerp(Quaternion(), 0.2 * (1.0 - rise)).to_euler('YZX')


# =========================================================================== binding
def _mirror(bone, side):
    return bone if side > 0 else ('r' + bone[1:] if bone[0] == 'l' else bone)


def _seg_dist(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared < 1e-9 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


def skin_object(ob, rig, bones, power=3.0, keep=3):
    """Weight a flexible part across 2-3 bones by inverse distance to their rest segments."""
    child = {}
    for b, p in reg.PARENT.items():
        child.setdefault(p, []).append(b)
    segs = {}
    for b in bones:
        a = Vector(reg.REST[b])
        ch = [k for k in child.get(b, []) if Vector(reg.REST[k]) != a]
        if b in getattr(reg, 'TAIL', {}):              # a childless bone states its own tail
            segs[b] = (a, Vector(reg.TAIL[b]))
        else:
            segs[b] = (a, Vector(reg.REST[ch[0]]) if ch else a + Vector((0, 0, 0.09)))
    groups = {b: ob.vertex_groups.new(name=b) for b in bones}
    M = ob.matrix_world
    for v in ob.data.vertices:
        p = M @ v.co
        w = {b: 1.0 / (max(_seg_dist(p, *segs[b]), 0.012) ** power) for b in bones}
        top = sorted(w.items(), key=lambda kv: -kv[1])[:keep]
        tot = sum(x for _, x in top)
        for b, x in top:
            groups[b].add([v.index], x / tot, 'REPLACE')
    mod = ob.modifiers.new('skin', 'ARMATURE')
    mod.object = rig
    ob['pc_bind'] = 'skin:' + ','.join(bones)
    return ob


def skin_hang(ob, rig, sewn, hang):
    """Weight a HANGING part between the body it is sewn to and its own cloth bone, by height.

    Inverse distance cannot do this job. A kimono sleeve is sewn to the body at the shoulder and
    hangs free below, so its top must stay with the shoulder and its bottom must obey gravity - but
    the top of the bag sits right on the shoulder bone, so by distance the shoulder wins everywhere
    and the whole bag swings over the head on an overhead cut. That is the bug this fixes.

    `sewn` keeps the seam; `hang` is the sleeve bone that engine-side hangCloth() aims at the ground.
    The blend is smoothstepped over the part's own height, so there is no crease where it changes."""
    gs = {b: ob.vertex_groups.new(name=b) for b in (sewn, hang)}
    M = ob.matrix_world
    zs = [(M @ v.co).z for v in ob.data.vertices]
    hi, lo = max(zs), min(zs)
    span = max(hi - lo, 1e-4)
    for v in ob.data.vertices:
        t = min(1.0, max(0.0, (hi - (M @ v.co).z) / span))
        t = t * t * (3.0 - 2.0 * t)                    # smoothstep: no crease at the seam
        gs[hang].add([v.index], t, 'REPLACE')
        gs[sewn].add([v.index], 1.0 - t, 'REPLACE')
    mod = ob.modifiers.new('skin', 'ARMATURE')
    mod.object = rig
    ob['pc_bind'] = f'hang:{sewn},{hang}'
    return ob


def parent_rigid(ob, joint):
    ob.parent = joint
    ob.matrix_parent_inverse = joint.matrix_world.inverted()
    ob['pc_bind'] = 'rigid'
    return ob


def skin_skirt(ob, rig, waist=0.93, hem=0.52, half=0.40, centre=1.0):
    """Weight a SKIRT (the hakama top: one cloth over both legs) between the hips and the two thighs.

    Inverse distance to the three bones tore it (28 Nov, blender/bench/body_sweep.py: edges stretched 4.3x, 267 edges
    past double in the extreme sweep): a vertex between the legs went to whichever thigh was nearer, so in a lunge the
    cloth over the crotch was pulled apart between a thigh going forward and one going back. Here the weights are
    smooth fields over the rest shape: the thighs take over with depth below the waist (smoothstep), more on the
    outside of each leg than in the middle (the middle keeps `centre` of it at most), shared left/right by a
    smoothstep across the body. Neighbouring vertices therefore always have neighbouring weights: nothing tears.
    Tuned on the extreme sweep (Kojiro, 7 poses): centre 0.35 / half 0.16 -> 409 edges past double; half 0.40, the
    hem fully on the legs (centre 1.0) -> 0, the worst edge 1.78x (was 4.3x). Dual-quaternion skinning was worse."""
    gs = {b: ob.vertex_groups.new(name=b) for b in ('hips', 'lthigh', 'rthigh')}
    M = ob.matrix_world

    def sm(t):
        t = min(1.0, max(0.0, t))
        return t * t * (3.0 - 2.0 * t)
    for v in ob.data.vertices:
        w = M @ v.co
        down = sm((waist - w.z) / (waist - hem))
        side = max(-1.0, min(1.0, w.x / half))
        legs = down * (centre + (1.0 - centre) * sm(abs(side)))
        left = sm((side + 1.0) / 2.0)
        gs['lthigh'].add([v.index], legs * left, 'REPLACE')
        gs['rthigh'].add([v.index], legs * (1.0 - left), 'REPLACE')
        gs['hips'].add([v.index], 1.0 - legs, 'REPLACE')
    mod = ob.modifiers.new('skin', 'ARMATURE')
    mod.object = rig
    ob['pc_bind'] = 'skirt:hips,lthigh,rthigh'
    return ob


def bind_foot_toe(ob, rig, foot, toe, band=0.03):
    """A FOOT split at the ball (28 Nov): what is ahead of the toe joint rides the toe bone, the heel the foot bone,
    blended over `band` metres across the ball so the fold never tears. A sandal was one rigid piece on the foot
    bone, so a rising heel lifted the whole sole off the ground on its tip (engine/footlock.js: toe-off 29 deg)."""
    gs = {b: ob.vertex_groups.new(name=b) for b in (foot, toe)}
    M = ob.matrix_world
    ball = Vector(reg.REST[toe])
    for v in ob.data.vertices:
        f = -((M @ v.co).y - ball.y)                   # metres ahead of the ball (the figure faces -Y)
        t = min(1.0, max(0.0, f / band + 0.5))
        t = t * t * (3.0 - 2.0 * t)
        gs[toe].add([v.index], t, 'REPLACE')
        gs[foot].add([v.index], 1.0 - t, 'REPLACE')
    mod = ob.modifiers.new('skin', 'ARMATURE')
    mod.object = rig
    ob['pc_bind'] = f'foot:{foot},{toe}'
    return ob


# =========================================================================== internal faces
def hide_internal_faces(objs, bind):
    """Delete faces sealed inside another RIGID part on the same bone: they never show and cost samples."""
    removed = 0
    rigid = [o for o in objs if bind.get(o.name, ('rigid', None))[0] == 'rigid' and o.type == 'MESH'
             and len(o.data.polygons) < 3000]
    trees = {}
    for o in rigid:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        trees[o.name] = (BVHTree.FromBMesh(bm), [v.co.copy() for v in bm.verts])
        bm.free()
    for a in rigid:
        for b in rigid:
            if a is b or bind[a.name][1] != bind[b.name][1]:
                continue
            if reg.PARTS.get(b.get('pc_part', ''), {}).get('layer', 0) <= \
               reg.PARTS.get(a.get('pc_part', ''), {}).get('layer', 0):
                continue
            tree = trees[b.name][0]
            bm = bmesh.new()
            bm.from_mesh(a.data)
            bm.transform(a.matrix_world)
            kill = []
            for f in bm.faces:
                c = f.calc_center_median()
                hits, o2 = 0, c
                for _ in range(6):                      # odd number of crossings = inside
                    r = tree.ray_cast(o2 + Vector((0, 0, 1e-4)), Vector((0.31, 0.47, 0.83)))
                    if r[0] is None:
                        break
                    hits += 1
                    o2 = r[0] + Vector((0.31, 0.47, 0.83)) * 1e-4
                if hits % 2 == 1:
                    kill.append(f)
            if kill and len(kill) < len(bm.faces):
                bm.transform(a.matrix_world.inverted())
                bmesh.ops.delete(bm, geom=kill, context='FACES')
                bm.to_mesh(a.data)
                removed += len(kill)
            bm.free()
    return removed


# =========================================================================== build
def build(recipe, *, pose='standing', location=(0, 0, 0), yaw=0.0, collection=None, name=None,
          seed=None, pose_overrides=None):
    """Build one character from a recipe dict. Returns {'rig','joints','objects','collection','recipe'}."""
    name = name or recipe.get('id', 'CHARACTER')
    scene = bpy.context.scene
    if collection is None:
        collection = bpy.data.collections.new(name)
        scene.collection.children.link(collection)
    rig = Rig(collection, name=name)
    glow = tuple(recipe.get('glow', (1.0, 0.55, 0.18)))
    glow_str = float(recipe.get('glow_strength', 3.0))
    ctx = reg.PartCtx(collection, seed=int(recipe.get('seed', 3) if seed is None else seed),
                      materials=recipe.get('paper', {}), glow=(glow, glow_str),
                      suffix='' if name == 'CHARACTER' else '_' + name,
                      proportion=recipe.get('proportion', 'standard'))
    bind, built, report = {}, [], []
    entries = sorted(recipe['parts'], key=lambda e: reg.PARTS[e['part']]['layer'])
    for entry in entries:
        key = entry['part']
        if key not in reg.PARTS:
            raise KeyError(f'recipe {name}: no such part {key!r} (see part_registry.py)')
        spec = reg.PARTS[key]
        scale = float(entry.get('scale', 1.0))
        lo, hi = spec['size']
        if not (lo - 1e-6 <= scale <= hi + 1e-6):
            raise ValueError(f'{key}: scale {scale} outside the approved range {lo}-{hi}')
        socks = entry.get('sockets') or spec['socket']
        for sock in socks:
            S = reg.SOCKETS[sock]
            ctx.socket = Vector(S['pos'])
            ctx.sock = sock
            ctx.side = S['side'] if S['side'] else 1
            before = set(ctx.objects)
            P = dict(spec['defaults'])
            P.update(entry.get('params', {}))
            spec['fn'](ctx, P, ctx.rnd)
            made = [o for o in ctx.objects if o not in before]
            bone = entry.get('bone') or spec['bone'] or S['bone']
            bones = [_mirror(b, ctx.side) for b in (entry.get('bones') or spec['bones'])] or [bone]
            for ob in made:
                ob['pc_recipe'] = key
                ob['pc_socket'] = sock
                if scale != 1.0:                       # scale the MESH about the socket: object scale stays 1
                    ob.data.transform(Matrix.Translation(ctx.socket) @ Matrix.Scale(scale, 4)
                                      @ Matrix.Translation(-ctx.socket))
                kind = 'rigid' if spec['rigid'] else (spec.get('skin') or 'skin')
                bind[ob.name] = (kind, bone, bones)
                built.append(ob)
            report.append(f'{key:<22}{sock:<14}{len(made)} objects  scale {scale:.2f}')
    bpy.context.view_layer.update()
    hidden = hide_internal_faces(built, {k: (v[0], v[1]) for k, v in bind.items()})
    for ob in built:
        kind, bone, bones = bind[ob.name]
        if kind == 'hang' and len(ob.data.vertices) and len(bones) >= 2:
            skin_hang(ob, rig.rig, bones[0], bones[1])   # bones = [sewn, cloth]
            ob.parent = rig.rig
        elif kind == 'skin' and set(bones) == {'hips', 'lthigh', 'rthigh'} and len(ob.data.vertices):
            skin_skirt(ob, rig.rig)                       # the hakama top: a skirt over two legs (28 Nov)
            ob.parent = rig.rig
        elif kind in ('skin', 'hang') and len(ob.data.vertices):
            skin_object(ob, rig.rig, bones)
            ob.parent = rig.rig
        elif bone in ('lfoot', 'rfoot') and len(ob.data.vertices):
            bind_foot_toe(ob, rig.rig, bone, bone[0] + 'toe')
            ob.parent = rig.rig
        else:
            parent_rigid(ob, rig.J[bone])
    rig.pose(pose, **(pose_overrides or {}))
    rig.J['root'].location = Vector(location) + rig.J['root'].location
    rig.J['root'].rotation_euler.rotate_axis('Z', yaw)
    bpy.context.view_layer.update()
    rig.sync_bones()
    # the inner lantern: the character is lit from inside, not only by the key light
    for nm, j, off, pw in (('chest', 'upper', (0, 0, 0.10), 3.2), ('belly', 'torso', (0, 0, 0.08), 0.5),
                           ('head', 'head', (0, 0, 0.08), 0.5)):
        L = bpy.data.lights.new(f'PC_lamp_{nm}_{name}', 'POINT')
        L.color = glow
        L.energy = pw * float(recipe.get('lamp_scale', 1.0))
        L.shadow_soft_size = 0.03
        lo = bpy.data.objects.new(L.name, L)
        collection.objects.link(lo)
        lo.parent = rig.J[j]
        lo.location = Vector(off)
    bpy.context.view_layer.update()
    print('\n'.join(report))
    print(f'[builder] {name}: {len(built)} objects, {hidden} internal faces removed, '
          f'{sum(len(o.data.polygons) for o in built)} faces')
    if recipe.get('surface'):
        # the paper surface upgrade (paper_materials.paper_surface): folds measured into each mesh, then ink in the
        # valleys, a light edge on the ridges, a printed mottle. Opt-in per recipe while it is tested (27 Nov).
        S_ = {k_: v_ for k_, v_ in recipe['surface'].items() if k_ != 'note'}     # a note documents, it is no input
        ang = float(S_.pop('angle', 28.0))
        n_folds, mats = 0, []
        for ob in built:
            if ob.type == 'MESH' and len(ob.data.polygons):
                n_folds += pm.add_fold_lines(ob, ang)
                mats += [s_.material for s_ in ob.material_slots if s_.material and s_.material not in mats]
        # dark papers (sumi hair, charcoal) get no light edge: on spiky black hair every ridge drew a grey scratch
        up = sum(1 for m_ in mats if pm.paper_surface(m_, **dict(S_, light=S_.get('light', 0.3) * (
            0.0 if any(k_ in m_.name.lower() for k_ in ('sumi', 'charcoal', 'black')) else 1.0))))
        print('[builder] %s: paper surface on %d materials, %d folds sharper than %.0f deg' % (name, up, n_folds, ang))
    return {'rig': rig, 'joints': rig.J, 'objects': built, 'collection': collection, 'recipe': recipe,
            'armature': rig.rig, 'bind': bind}


def load_recipe(path):
    with open(path) as fh:
        r = json.load(fh)
    base = r.get('extends')
    if base:
        p = base if os.path.isabs(base) else os.path.join(os.path.dirname(os.path.abspath(path)), base)
        parent = load_recipe(p if p.endswith('.json') else p + '.json')
        merged = dict(parent)
        merged.update({k: v for k, v in r.items() if k != 'extends'})
        if 'swap' in r or 'add' in r or 'drop' in r:
            # Swap by SLOT (one kasa, one torso, one obi…), except the slots that legitimately hold several
            # parts at once — there armour and accessories are swapped, added and dropped BY NAME.
            # A ONE-SIDED part (one socket ending .L or .R: a generated left sleeve) is keyed by slot AND side, so
            # a recipe can hold a left and a right sleeve; keyed by slot alone the right one silently replaced the
            # left (27 Nov: kojiro-ai2 and musashi-ai built one sleeve, one leg and one foot). A one-sided part
            # replaces a two-sided part of its slot (the folded sleeve builds both sides), and the other way round.
            multi = {'armor', 'accessory'}

            def side(e):
                socks = reg.PARTS[e['part']]['socket']
                socks = [socks] if isinstance(socks, str) else list(socks)
                return socks[0].rsplit('.', 1)[1] if len(socks) == 1 and socks[0][-2:] in ('.L', '.R') else None

            def k(e):
                sl = reg.PARTS[e['part']]['slot']
                if sl in multi:
                    return e['part']
                sd = side(e)
                return f'{sl}.{sd}' if sd else sl

            def put(kit, e):
                key, sl = k(e), reg.PARTS[e['part']]['slot']
                if sl not in multi:
                    for kk in [kk for kk in kit if (kk.startswith(sl + '.') if key == sl else kk == sl)]:
                        kit.pop(kk)
                kit[key] = e
            kit = {k(e): e for e in merged['parts']}
            for e in r.get('swap', []):
                put(kit, e)
            for name in r.get('drop', []):
                kit.pop(name, None)
                for key, e in list(kit.items()):
                    if e['part'] == name or reg.PARTS[e['part']]['slot'] == name:
                        kit.pop(key, None)
            for e in r.get('add', []):
                put(kit, e)
            merged['parts'] = list(kit.values())
        r = merged
    return r


# =========================================================================== lighting + render
def studio(scene, kind='neutral', coll=None):
    """neutral = the flat studio that hides nothing (the one the models were audited under);
       cinematic = the dark Lantern Origami key, where the paper glows from inside."""
    coll = coll or scene.collection
    w = bpy.data.worlds.new('PC_World')
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    if kind == 'neutral':
        bg.inputs[0].default_value = (0.55, 0.56, 0.58, 1)
        bg.inputs[1].default_value = 1.4
        rig = (((-2.5, -3, 3.2), 400, 2.5, (1, 1, 1)), ((3, -1.5, 2), 160, 2, (1, 1, 1)),
               ((0, 3.5, 2.5), 200, 3, (1, 1, 1)))
        exposure = 0.0
    else:
        bg.inputs[0].default_value = (0.010, 0.012, 0.020, 1)
        bg.inputs[1].default_value = 0.35
        rig = (((-2.2, -2.4, 2.9), 160, 1.2, (1.0, 0.95, 0.88)),
               ((2.6, 1.9, 2.4), 110, 1.0, (0.70, 0.80, 1.0)),
               ((0.4, -3.4, 0.5), 14, 1.5, (1.0, 0.72, 0.42)))
        exposure = -0.35
    for loc, e, sz, col in rig:
        L = bpy.data.lights.new('L', 'AREA')
        L.energy, L.size, L.color = e, sz, col
        o = bpy.data.objects.new('L', L)
        # Not visible to camera rays. An area lamp renders as a bright rectangle if it ever lands in
        # shot; in an empty studio it never does, which is how one reached a finished frame.
        o.visible_camera = False
        o.location = loc
        o.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        coll.objects.link(o)
    try:
        scene.view_settings.view_transform = 'AgX'
    except Exception:
        pass
    scene.view_settings.exposure = exposure
    return scene


def render_settings(scene, res='420x740', samples=24):
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = int(samples)
    scene.cycles.use_denoising = True
    scene.cycles.device = 'CPU'
    x, y = res.split('x')
    scene.render.resolution_x, scene.render.resolution_y = int(x), int(y)
    scene.render.resolution_percentage = 100
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2


def camera(scene, pos, look, lens=70, coll=None):
    cd = bpy.data.cameras.new('PC_cam')
    cd.lens = lens
    c = bpy.data.objects.new('PC_cam', cd)
    (coll or scene.collection).objects.link(c)
    c.location = pos
    c.rotation_euler = (Vector(look) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = c
    return c


def render(scene, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    scene.render.filepath = os.path.abspath(path)
    bpy.ops.render.render(write_still=True)
    print('wrote', path)
    return path


def frame(objs):
    """Centre and height of what was actually built, so a turnaround always fills the frame."""
    lo = Vector((9e9, 9e9, 9e9))
    hi = Vector((-9e9, -9e9, -9e9))
    for o in objs:
        if o.type != 'MESH' or not len(o.data.vertices):
            continue
        for v in o.bound_box:
            w = o.matrix_world @ Vector(v)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return (0.0, 0.0, (lo.z + hi.z) / 2), max(hi.z - lo.z, 0.5)


VIEWS = (('front', 0), ('three-quarter', 40), ('side', 90), ('back', 180))


def turnaround(scene, out, center=(0, 0, 0.95), dist=4.3, lens=70, views=VIEWS, eye=None):
    files = []
    for nm, deg in views:
        a = math.radians(deg)
        camera(scene, (-math.sin(a) * dist, -math.cos(a) * dist,
                       center[2] + 0.12 if eye is None else eye), center, lens)
        # A path without .png used to have nothing to replace, so every view wrote to the SAME
        # file and four renders silently became one. Build the name instead of patching it.
        base = out[:-4] if out.lower().endswith('.png') else out.rstrip('/') + '/view'
        files.append(render(scene, f'{base}-{nm}.png'))
    return files


# =========================================================================== CLI
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    rpath = arg('recipe')
    if not rpath:
        print('usage: --recipe library/character-recipes/<id>.json [--out x.blend] [--pose p] '
              '[--still p.png | --turnaround p.png] [--light neutral|cinematic]')
        return
    recipe = load_recipe(os.path.abspath(rpath))
    ch = build(recipe, pose=arg('pose', recipe.get('pose', 'neutral')),
               pose_overrides=None if arg('pose') else recipe.get('pose_overrides'), yaw=math.radians(float(arg('ry', 0))))
    if arg('still') or arg('turnaround'):
        studio(scene, arg('light', 'neutral'))
        render_settings(scene, arg('res', '420x740'), arg('samples', 24))
        if (arg('engine') or '').lower() == 'eevee':        # the films' engine (render_engine.setup_render)
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from render_engine import setup_render
            setup_render(scene, engine='eevee', samples=int(arg('samples', 24)))
        center, height = frame(ch['objects'])
        if arg('poses'):
            # a pose sweep (or a slash): one still per pose, same camera, so motion is the only variable
            a = math.radians(float(arg('angle', 34)))
            d = float(arg('dist', 0) or height * 2.55)
            camera(scene, (-math.sin(a) * d, -math.cos(a) * d, center[2] + 0.12), center,
                   float(arg('lens', 70)))
            out = arg('poses_out') or arg('still') or 'output/character/pose.png'
            for nm in arg('poses').split(','):
                ch['rig'].pose(nm, **(recipe.get('pose_overrides', {}) if nm == 'neutral' else {}))
                c2, h2 = frame(ch['objects'])      # re-frame: the pose is the subject, not the framing
                d2 = float(arg('dist', 0) or h2 * 2.55)
                camera(scene, (-math.sin(a) * d2, -math.cos(a) * d2, c2[2] + 0.12), c2,
                       float(arg('lens', 70)))
                render(scene, out.replace('.png', f'-{nm}.png'))
        elif arg('turnaround'):
            turnaround(scene, arg('turnaround'), center=center,
                       dist=float(arg('dist', 0) or height * 2.55), lens=float(arg('lens', 70)))
        else:
            a = math.radians(float(arg('angle', 28)))
            d = float(arg('dist', 0) or height * 2.55)
            camera(scene, (-math.sin(a) * d, -math.cos(a) * d, center[2] + 0.12), center,
                   float(arg('lens', 70)))
            render(scene, arg('still'))
    if arg('out'):
        os.makedirs(os.path.dirname(os.path.abspath(arg('out'))), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(arg('out')))
        print('saved', arg('out'))


if __name__ == '__main__':
    main()
