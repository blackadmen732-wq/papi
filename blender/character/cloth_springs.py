"""CLOTH SPRINGS: the clothes get weight and momentum (Mark, 26 Nov: "why does the paper not move when the
body moves ... the clothes don't feel realistic ... everything don't have their space").

Why they were stiff: the cloth joints (the two sleeves, the hakama) were AIMED every frame by a fixed rule
(Rig._hang_sleeves, the pose's 'sway' number). Aiming has no memory, so when the body turns fast the cloth
turns at the same instant, like a statue. Real cloth lags behind, swings past and settles.

What studios do (games call it spring bones / dynamic bones, film calls it secondary motion or a cloth pass):
each cloth bone gets a weight at its tip that is pulled toward where the rule wants it by a spring, slowed
by damping, pulled down by gravity, and kept OUT of the body by the collision capsules. Run frame by frame
over the finished animation, it gives follow-through (the sleeve trails a swing and overshoots), drag (the
hakama lags a turn), and space (a sleeve can't sink into the chest or the legs). It is deterministic: the
same animation always gives the same cloth, so renders match.

  springs = ClothSprings(rig, caps, fps=30)   # caps: body_capsules.BodyCapsules
  ...each frame, AFTER the final rig.pose(...) of that frame:
  springs.step()
"""
import math

import bpy
from mathutils import Vector

DOWN = Vector((0.0, 0.0, -1.0))          # a cloth joint's hanging axis in its own frame

# joint, tip length m, stiffness (1/s^2), damping (1/s), max swing from the rule's aim (deg), capsules to ignore
SPRINGS = (
    ('rSleeve', 0.24, 55.0, 7.0, 75.0, ('forearm.R', 'upperarm.R')),
    ('lSleeve', 0.24, 55.0, 7.0, 75.0, ('forearm.L', 'upperarm.L')),
    ('hakama', 0.75, 38.0, 8.0, 22.0, ('belly', 'hips', 'thigh.R', 'thigh.L', 'shin.R', 'shin.L')),
)

# LAYERED PLATES (blender/character/layered_garment.py, AUTOPILOT item 17): every joint the builder made for a
# layered garment carries `pc_plate` (its place in the chain) and gets its own spring, softer down the chain so a
# swing reaches the lower plates later. Knots from the cloth bench (tools/cloth_bench.py): 55/42/31/22 for 4 plates.
PLATE_K = (55.0, 42.0, 31.0, 22.0)
PLATE_DAMPING, PLATE_MAX_DEG = 7.0, 75.0
# The spring pulls on the TIP's position, so its angular pull against gravity, wind and the arm's acceleration scales
# with the tip length: a 4.5 cm band on a 4.5 cm tip flopped up to 178 deg on Kojiro's strike (28 Nov bench). The
# stiffnesses above were tuned on the cloth bench's 12 cm plates, so a plate's spring runs at least that long.
PLATE_TIP_M = 0.12


def plate_stiffness(j, n):
    if n <= 1:
        return PLATE_K[0]
    x = j * (len(PLATE_K) - 1) / (n - 1)
    i = min(int(x), len(PLATE_K) - 2)
    return PLATE_K[i] + (PLATE_K[i + 1] - PLATE_K[i]) * (x - i)


def plate_springs(rig):
    """The SPRINGS entries for a rig's layered plates, parent first (plate j after plate j-1)."""
    out = []
    for name, e in rig.J.items():
        if 'pc_plate' in e:
            sd = str(e.get('pc_plate_side', 'R'))
            out.append((int(e['pc_plate']), name, max(PLATE_TIP_M, float(e['pc_plate_len'])),
                        plate_stiffness(int(e['pc_plate']), int(e['pc_plates'])), PLATE_DAMPING, PLATE_MAX_DEG,
                        ('forearm.' + sd, 'upperarm.' + sd)))
    return [t[1:] for t in sorted(out, key=lambda t: (t[0], t[1]))]


class ClothSprings:
    def __init__(self, rig, caps=None, fps=30, springs=SPRINGS, gravity=9.8, margin=0.015, panels=None, body=None):
        """panels: {joint: [mesh objects]} - the actual paper of that cloth bone. body: the PERSON's capsules.
        With both, every frame the deformed paper itself is checked, and the cloth bone swings away until no
        corner of the panel is inside the body (a bone tip can be clear while a panel corner still cuts in)."""
        self.panels, self.body = panels or {}, body
        self.rig, self.caps, self.dt = rig, caps, 1.0 / fps
        self.spec = [s for s in springs if s[0] in rig.J]
        have = {s[0] for s in self.spec}
        for sp in plate_springs(rig):                # a layered garment's plates (none on a recipe without "layers")
            if sp[0] not in have:
                self.spec.append(sp)
                if body is not None and sp[0] not in self.panels:
                    self.panels[sp[0]] = [c for c in rig.J[sp[0]].children if c.type == 'MESH']
        self.g, self.margin = gravity, margin
        self.state = {}                              # joint -> (tip position, velocity)
        self.log = {}                                # joint -> list of (lag deg, pushed out?)
        self.depths = {}                             # joint -> list of (rule tip inside m, spring tip inside m)
        self.wind = None                             # film.wind: {to: [x, y] world, strength m/s^2, gust 0-1, seed}
        self.frame = 0
        self.roots = {}                              # joint -> its root last frame (to see a teleport at a cut)
        self.resets = []                             # (frame, joint) where a teleport restarted the cloth
        self.hinge_inside = []                       # (frame, plate) whose hinge was inside the body: not cleared

    def wind_at(self, t):
        """The wind's push on a cloth tip at time t (world m/s^2): a steady part plus slow gusts and a flutter, the
        same for every run (a pure function of t). The sleeves' stiffness turns 4 m/s^2 into ~15 degrees of lean."""
        W = self.wind
        if not W:
            return Vector((0, 0, 0))
        d = Vector((float(W['to'][0]), float(W['to'][1]), 0.0)).normalized()
        g = float(W.get('gust', 0.5))
        ph = float(W.get('seed', 0)) * 1.7
        gust = 0.55 + 0.45 * math.sin(2 * math.pi * t / 4.3 + ph) * math.sin(2 * math.pi * t / 1.7 + 0.6 * ph)
        flutter = 0.12 * math.sin(2 * math.pi * t * 5.3 + ph) + 0.08 * math.sin(2 * math.pi * t * 8.9 + 2 * ph)
        side = Vector((-d.y, d.x, 0.0)) * (0.25 * math.sin(2 * math.pi * t / 2.9 + ph))
        return (d * ((1 - g) + g * gust + flutter) + side) * float(W.get('strength', 3.0))

    def _aim(self, e, world_dir):
        pq = e.parent.matrix_world.to_quaternion()
        local = (pq.inverted() @ world_dir).normalized()
        e.rotation_euler = DOWN.rotation_difference(local).to_euler('YZX')

    def _clear_panel(self, name, e, root, L, skip, step_deg=8.0, iters=16):
        from mathutils import Matrix
        body = self.body.update()
        for _ in range(iters):
            bpy.context.view_layer.update()
            self.rig.sync_bones()
            dg = bpy.context.evaluated_depsgraph_get()
            worst, wpt = 0.0, None
            for ob in self.panels[name]:
                me = ob.evaluated_get(dg).to_mesh()
                mw = ob.matrix_world
                for v in me.vertices:
                    w = mw @ v.co
                    d, _who = body.depth(w, skip=skip)
                    if d > worst:
                        worst, wpt = d, w
                ob.evaluated_get(dg).to_mesh_clear()
            if worst <= 0:
                break
            away = body.push_out(wpt, 0.01, skip=skip) - wpt
            arm = wpt - root
            axis = arm.cross(away)
            if axis.length < 1e-9:
                break
            d = (e.matrix_world.to_quaternion() @ DOWN).normalized()
            d = (Matrix.Rotation(math.radians(step_deg), 3, axis.normalized()) @ d).normalized()
            self._aim(e, d)
        bpy.context.view_layer.update()
        return root + (e.matrix_world.to_quaternion() @ DOWN).normalized() * L

    def step(self):
        self.frame += 1
        wind = self.wind_at(self.frame * self.dt)
        bpy.context.view_layer.update()
        if self.caps is not None:
            self.caps.update()
        for name, L, k, c, max_deg, skip in self.spec:
            e = self.rig.J[name]
            if 'pc_plate' in e:
                # a plate's rule: the hang line of the whole chain, where the ARM carries plate 0 (as tools/cloth_bench.py
                # LAYERED). The plate above carries only its hinge; aiming at the plate above stacked every plate's
                # lean on the next (175 deg at the hem on Kojiro's strike). Set every frame, or last frame's swing
                # would become this frame's aim and the spring would have nothing to pull back to.
                b = e
                while 'pc_plate' in b.parent:
                    b = b.parent
                from mathutils import Euler
                chain = (b.parent.matrix_world.to_quaternion()
                         @ Euler(tuple(b['pc_rest_rot']), 'YZX').to_quaternion() @ DOWN).normalized()
                self._aim(e, chain)
                bpy.context.view_layer.update()
            root = e.matrix_world.translation.copy()
            want = (e.matrix_world.to_quaternion() @ DOWN).normalized()   # where the rule aims it now
            goal = root + want * L
            # a teleport at a cut (the root moved more than 15 m/s in one frame): the cloth starts again at rest where
            # the body now is, instead of swinging toward the place it left (a flick on the new shot's first frame)
            last = self.roots.get(name)
            self.roots[name] = root.copy()
            if name not in self.state or (last is not None and (root - last).length > 0.5):
                self.state[name] = (goal.copy(), Vector((0, 0, 0)))
                if last is not None:
                    self.resets.append((self.frame, name))
            p, v = self.state[name]
            # sub-steps keep a stiff spring stable at 30 fps
            n = 4
            h = self.dt / n
            for _ in range(n):
                a = (goal - p) * k - v * c + Vector((0, 0, -self.g)) * 0.15 + wind
                v = v + a * h
                p = p + v * h
                # the tip stays at the cloth's length from its root
                d = p - root
                p = root + (d.normalized() if d.length > 1e-9 else want) * L
            # never swing further than max_deg from the rule's aim (paper is stiff, not silk)
            d = (p - root).normalized()
            ang = d.angle(want, 0.0)
            if ang > math.radians(max_deg):
                axis = want.cross(d)
                if axis.length > 1e-9:
                    from mathutils import Quaternion
                    d = Quaternion(axis.normalized(), math.radians(max_deg)) @ want
                    p = root + d * L
            pushed = False
            if self.caps is not None:
                for _ in range(6):                           # push out, keep the length, until it stays out
                    q = self.caps.push_out(p, self.margin, skip=skip)
                    if (q - p).length < 1e-5:
                        break
                    pushed = True
                    v = v - (q - p) / self.dt * 0.5          # lose the speed that went into the body
                    p = root + (q - root).normalized() * L
            if self.caps is not None:
                before = self.caps.depth(goal, skip=skip)[0]
                after = self.caps.depth(p, skip=skip)[0]
                self.depths.setdefault(name, []).append((max(0.0, before), max(0.0, after)))
            self.state[name] = (p, v)
            self._aim(e, (p - root).normalized())
            hinge_in = 'pc_plate' in e and self.body is not None and self.body.update().depth(root, skip=skip)[0] > 0
            if hinge_in:                             # a plate hinged INSIDE the body (its arm is in the chest): no
                self.hinge_inside.append((self.frame, name))   # turn can clear it, the search only spins the plate
            if name in self.panels and self.body is not None and not hinge_in:
                p = self._clear_panel(name, e, root, L, skip)
                self.state[name] = (p, self.state[name][1])
            self.log.setdefault(name, []).append((round(math.degrees((p - root).normalized().angle(want, 0.0)), 1),
                                                  pushed))
        bpy.context.view_layer.update()
