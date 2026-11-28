"""PART REGISTRY: the Modular Origami Character Factory's library of folded paper parts.

One skeleton, many interchangeable parts, one material family. Every part is a function registered with
@part(...), which declares everything the builder and the validator need to know about it:

    slot          where it goes (hat, face, hair, torso, collar, obi, sleeve_upper, sleeve_hanging, forearm,
                  hand, thigh, shin, foot, armor, accessory)
    socket        the attachment point in the rig's REST pose (position + orientation, see SOCKETS)
    bone/bones    the bone it binds to (rigid) or the 2-3 bones it is weighted across (flexible)
    rigid         True = parented to one bone, False = skinned across `bones`
    size          the approved uniform scale range (min, max); a recipe may not go outside it
    layer         draw/layer order: a higher number sits OVER a lower one (skin 0 … hat 90)
    material      the sheet it wants from library/paper-materials/ (a recipe may override)
    proportions   the body proportions it is cut for

    python3 blender/character/part_registry.py            # the whole library as a table
    python3 blender/character/part_registry.py --slots    # the slot table only

Every part is built as a FOLDED SHELL: flat facets, real thickness (solidify, the rim gets its own material so
the cut edge of the sheet reads), neighbours that OVERLAP at the joints, and a dark seam gap (`seam_shadow`)
wherever two sheets meet — the three things that make the reference read as separate sheets of paper rather
than one fused blob.

Geometry is built in the rig's REST world space (metres, Z up, the character faces -Y), around the part's
socket. The builder (modular_builder.py) scales, binds and poses it.
"""
import json
import math
import os
import random
import sys

try:
    import bmesh
    import bpy
    from mathutils import Matrix, Vector
    HAVE_BPY = True
except ImportError:                        # `python3 part_registry.py` outside Blender
    HAVE_BPY = False
    Vector = tuple

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(HERE, '..', 'world'))
if HAVE_BPY:
    import paper_materials as pm  # noqa: E402

# =========================================================================== the shared skeleton
# Joint rest positions in Blender world space (metres). Same joints and same names as engine/figure.js and
# blender/character/rig_trellis.py, so library/poses.json drives this rig directly.
REST = {
    'root': (0.00, 0.0, 0.00), 'hips': (0.00, 0.0, 0.92), 'torso': (0.00, 0.0, 0.92),
    'upper': (0.00, 0.0, 1.18), 'neck': (0.00, 0.0, 1.47), 'head': (0.00, 0.0, 1.53),
    'hakama': (0.00, 0.0, 0.92),
    'lC': (0.07, 0.0, 1.39), 'lS': (0.23, 0.0, 1.39), 'lE': (0.23, 0.0, 1.09),
    'lT': (0.23, 0.0, 1.09), 'lH': (0.23, 0.0, 0.80), 'lSleeve': (0.23, 0.0, 0.99),
    'rC': (-0.07, 0.0, 1.39), 'rS': (-0.23, 0.0, 1.39), 'rE': (-0.23, 0.0, 1.09),
    'rT': (-0.23, 0.0, 1.09), 'rH': (-0.23, 0.0, 0.80), 'rSleeve': (-0.23, 0.0, 0.99),
    'lthigh': (0.10, 0.0, 0.92), 'lshin': (0.10, 0.0, 0.46), 'lfoot': (0.10, 0.0, 0.02),
    'rthigh': (-0.10, 0.0, 0.92), 'rshin': (-0.10, 0.0, 0.46), 'rfoot': (-0.10, 0.0, 0.02),
}
# Bones whose tail cannot be guessed from a child joint, because they have no child. Without this a
# childless bone gets a stub tail pointing straight up (see modular_builder._build_armature), which
# both leaves its rest orientation wrong and, since skin weights are inverse distance to the bone's
# rest SEGMENT, hands its own cloth to the arm bones instead. The sleeve bone runs DOWN the tamoto.
TAIL = {'lSleeve': (0.23, 0.0, 0.74), 'rSleeve': (-0.23, 0.0, 0.74)}

PARENT = {'hips': 'root', 'torso': 'hips', 'upper': 'torso', 'neck': 'upper', 'head': 'neck', 'hakama': 'hips',
          'lC': 'upper', 'lS': 'lC', 'lE': 'lS', 'lT': 'lE', 'lH': 'lT', 'lSleeve': 'lT',
          'rC': 'upper', 'rS': 'rC', 'rE': 'rS', 'rT': 'rE', 'rH': 'rT', 'rSleeve': 'rT',
          'lthigh': 'root', 'lshin': 'lthigh', 'lfoot': 'lshin',
          'rthigh': 'root', 'rshin': 'rthigh', 'rfoot': 'rshin'}

# --------------------------------------------------------------------------- sockets
# A socket is where a part clips on: a position in the rest pose, the direction the part grows in ('up',
# 'down', 'out', 'front'), the bone under it, and the body radius there (so a part can be cut to fit).
def _socket(pos, bone, grow='down', radius=0.12, side=0):
    return dict(pos=tuple(pos), bone=bone, grow=grow, radius=radius, side=side)


SOCKETS = {
    'head_top':   _socket((0, 0.00, 1.585), 'head', 'up', 0.11),
    'face':       _socket((0, -0.03, 1.625), 'head', 'front', 0.11),
    'hair_back':  _socket((0, 0.05, 1.63), 'head', 'back', 0.10),
    'neck':       _socket((0, 0.00, 1.47), 'neck', 'up', 0.055),
    'collar':     _socket((0, -0.06, 1.36), 'upper', 'down', 0.17),
    'chest':      _socket((0, 0.00, 1.18), 'upper', 'up', 0.22),
    'waist':      _socket((0, 0.00, 0.92), 'torso', 'up', 0.18),
    'obi':        _socket((0, 0.00, 0.94), 'torso', 'up', 0.20),
    'back':       _socket((0, 0.11, 1.22), 'torso', 'back', 0.10),
    'hip_side.L': _socket((0.185, -0.055, 0.945), 'torso', 'out', 0.06, side=1),
    'hip_side.R': _socket((-0.185, -0.055, 0.945), 'torso', 'out', 0.06, side=-1),
    'shoulder.L': _socket((0.23, 0.00, 1.39), 'lS', 'down', 0.085, side=1),
    'shoulder.R': _socket((-0.23, 0.00, 1.39), 'rS', 'down', 0.085, side=-1),
    'elbow.L':    _socket((0.23, 0.00, 1.09), 'lT', 'down', 0.075, side=1),
    'elbow.R':    _socket((-0.23, 0.00, 1.09), 'rT', 'down', 0.075, side=-1),
    'hand.L':     _socket((0.23, 0.00, 0.80), 'lH', 'down', 0.045, side=1),
    'hand.R':     _socket((-0.23, 0.00, 0.80), 'rH', 'down', 0.045, side=-1),
    'hip.L':      _socket((0.10, 0.00, 0.92), 'lthigh', 'down', 0.16, side=1),
    'hip.R':      _socket((-0.10, 0.00, 0.92), 'rthigh', 'down', 0.16, side=-1),
    'knee.L':     _socket((0.10, 0.00, 0.46), 'lshin', 'down', 0.17, side=1),
    'knee.R':     _socket((-0.10, 0.00, 0.46), 'rshin', 'down', 0.17, side=-1),
    'ankle.L':    _socket((0.10, 0.00, 0.02), 'lfoot', 'front', 0.07, side=1),
    'ankle.R':    _socket((-0.10, 0.00, 0.02), 'rfoot', 'front', 0.07, side=-1),
}

SLOTS = {   # slot: (what it is, default layer, is it usually flexible)
    'hat': ('head covering: kasa, hachigane, hood', 90, False),
    'face': ('the folded mask: nose ridge, eye slits, chin', 40, False),
    'hair': ('folded hair / topknot at the back of the head', 35, False),
    'neck': ('the neck column between collar and mask', 30, False),
    'torso': ('the kimono body: the sheets the rest layers onto', 20, False),
    'collar': ('eri: the crossed lapels, left over right', 45, False),
    'obi': ('the sash with its knot and cord', 50, False),
    'sleeve_upper': ('the upper arm sleeve', 25, False),
    'sleeve_hanging': ('tamoto: the wide hanging sleeve bag', 55, True),
    'forearm': ('the forearm sleeve or kote', 25, False),
    'hand': ('folded fingers', 15, False),
    'thigh': ('hakama upper leg', 22, True),
    'shin': ('hakama lower leg', 22, True),
    'foot': ('tabi + zori', 18, False),
    'armor': ('plates over the paper: sode, do, kusazuri', 60, False),
    'accessory': ('katana, cords, tassels, straps', 70, False),
}

PARTS = {}


def part(name, *, slot, socket, bone=None, bones=None, rigid=True, size=(0.9, 1.1), layer=None,
         material='washi_natural', rim='washi_shade', proportions=('standard',), tags=(), skin=None,
         **defaults):
    """Register a part. `defaults` doubles as its documented parameter list."""
    def deco(fn):
        if slot not in SLOTS:
            raise KeyError(f'{name}: unknown slot {slot!r}')
        socks = socket if isinstance(socket, (list, tuple)) else [socket]
        for s in socks:
            if s not in SOCKETS:
                raise KeyError(f'{name}: unknown socket {s!r}')
        PARTS[name] = dict(
            name=name, fn=fn, slot=slot, socket=socks, bone=bone, bones=list(bones or []), rigid=rigid,
            skin=skin,
            size=tuple(size), layer=SLOTS[slot][1] if layer is None else layer, material=material, rim=rim,
            proportions=tuple(proportions), tags=tuple(tags), defaults=defaults,
            doc=(fn.__doc__ or '').strip().split('\n')[0])
        return fn
    return deco


# =========================================================================== folding tools
# Everything here makes CRISP PAPER: straight creases, flat facets, low vertex counts, no smooth shading.
def V(x, y, z):
    return Vector((x, y, z))


def poly_ring(n, r, z, *, cx=0.0, cy=0.0, flute=0.0, sy=1.0, phase=0.0, front_pull=0.0, lift=0.0):
    """One ring of a folded tube. `flute` pushes every second vertex in and `lift` pushes it up: together
    that is a real pleat (a fold with a ridge and a valley), not a wobble in a curve."""
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n + phase
        odd = i % 2
        rr = r * (1 - flute if odd else 1.0)
        z = z + lift if odd else z - (lift if lift else 0.0)
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a) * sy
        if front_pull and math.sin(a) < 0:
            y -= front_pull * -math.sin(a)
        out.append((x, y, z))
        if lift:
            z = z - lift if odd else z + lift
    return out


def skin_rings(bm, rings, *, close=True, cap_first=False, cap_last=False):
    """Bridge a stack of equal-length rings into a folded tube."""
    vs = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(vs[0])
    for a, b in zip(vs, vs[1:]):
        for i in range(n if close else n - 1):
            j = (i + 1) % n
            try:
                bm.faces.new((a[i], a[j], b[j], b[i]))
            except ValueError:
                pass
    if cap_first:
        bm.faces.new(vs[0][::-1])
    if cap_last:
        bm.faces.new(vs[-1])
    return vs


def shell(points, faces):
    """A folded shell straight from a vertex list: the honest way to make a crease you can point at."""
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in points]
    for f in faces:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    return bm


def panel(pts, *, bulge=0.0, normal=(0, -1, 0)):
    """A flat folded panel (an n-gon). `bulge` lifts its centre along the normal: one soft crease, no curve."""
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in pts]
    f = bm.faces.new(vs)
    if bulge:
        c = sum((Vector(p) for p in pts), Vector()) / len(pts)
        bmesh.ops.poke(bm, faces=[f])
        for v in bm.verts:
            if (Vector(v.co) - c).length < 1e-5:
                v.co += Vector(normal).normalized() * bulge
    return bm


def box(cx, cy, cz, sx, sy, sz, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    m = Matrix.Rotation(rot[0], 3, 'X') @ Matrix.Rotation(rot[1], 3, 'Y') @ Matrix.Rotation(rot[2], 3, 'Z')
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=m)
    bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=bm.verts)
    return bm


def join(bm, other):
    me = bpy.data.meshes.new('_tmp')
    other.to_mesh(me)
    other.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    return bm


def creases(bm, *, inset=0.004, depth=-0.0022, share=1.0, rnd=None):
    """Score a thin groove around facets: the valley the light catches at every fold. Material index 1."""
    rnd = rnd or random
    faces = [f for f in bm.faces if rnd.random() < share]
    if not faces:
        return
    bmesh.ops.inset_individual(bm, faces=faces, thickness=inset, depth=depth, use_even_offset=True)
    inner = set(faces)
    for f in bm.faces:
        if f not in inner:
            f.material_index = 1


# =========================================================================== build context
class PartCtx:
    """What a part builder is handed: the collection, the socket it hangs on, materials and a seeded stream."""

    def __init__(self, coll, *, seed=1, materials=None, glow=((1.0, 0.55, 0.18), 3.0), scale=1.0,
                 suffix='', proportion='standard'):
        self.coll = coll
        self.rnd = random.Random(seed)
        self.seed = seed
        self.glow = glow
        self.scale = scale
        self.suffix = suffix
        self.proportion = proportion
        self.overrides = materials or {}
        self._mats = {}
        self.socket = Vector((0, 0, 0))
        self.sock = None
        self.side = 1
        self.objects = []

    # ---- materials: one family, world-scale fibre, every sheet from library/paper-materials/
    def mat(self, key, *, glow=None, color=None):
        key = self.overrides.get(key, key)
        return pm.PC_Washi_Master(key, scale=1.0, suffix=self.suffix,
                                  glow=(self.glow if glow is True else glow), color=color)

    def lit(self, k=1.0):
        """The inner-light response scaled down: big outer sheets take none (form first), sheets seen from
        INSIDE (sleeve mouths, the collar well, under the hem) take a little, so the lantern reads as inside."""
        return (self.glow[0], self.glow[1] * k) if k > 0 else None

    def emit(self, key='glow', strength=None):
        nm = 'PC_Glow_' + key + self.suffix
        nm += '' if strength is None else '_%d' % round(strength * 10)
        m = bpy.data.materials.get(nm)
        if m is None:
            m = pm.emission_material(nm, self.glow[0], self.glow[1] if strength is None else strength)
        return m

    # ---- geometry
    def add(self, name, bm, mats, *, thickness=0.006, flat=True, rim_mat=True, to_camera=True):
        """Turn a bmesh into a part object: thickness, hard facets, per-facet tone, a cut paper edge."""
        me = bpy.data.meshes.new(name + self.suffix)
        bm.normal_update()
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name + self.suffix, me)
        for m in mats:
            me.materials.append(m)
        self.coll.objects.link(ob)
        pm.add_facet_attribute(ob, seed=self.rnd.randint(0, 9999))
        if flat:
            for p in me.polygons:
                p.use_smooth = False
        if thickness:
            mod = ob.modifiers.new('fold', 'SOLIDIFY')
            mod.thickness = thickness
            mod.offset = 0.0
            mod.use_even_offset = True
            mod.thickness_clamp = 1.0
            if rim_mat and len(me.materials) > 1:
                mod.material_offset_rim = 1       # the cut edge of the sheet gets its own tone
        ob['pc_part'] = name
        if not to_camera:          # a lantern inside the paper: it LIGHTS, it is never seen as a white box
            ob.visible_camera = False
            ob.visible_shadow = False
            ob['pc_internal'] = 1
        self.objects.append(ob)
        return ob

    def gap(self, name, pts, push=(0, 0.006, 0), grow=0.008):
        """The dark slot behind an overlap: without it two sheets read as one moulded lump."""
        c = sum((Vector(p) for p in pts), Vector()) / len(pts)
        out = [tuple(Vector(p) + (Vector(p) - c).normalized() * grow + Vector(push)) for p in pts]
        return self.add(name, panel(out), [self.mat('seam_shadow')], thickness=0.0015, rim_mat=False)


# =========================================================================== PARTS: head
@part('kasa_wide', slot='hat', socket='head_top', bone='head', size=(0.85, 1.15), material='washi_hat',
      ribs=22, radius=0.40, rise=0.255, brim_lift=0.075, rim_roll=0.013, tags=('reference',),
      proportions=('slim', 'standard', 'broad'))
def kasa_wide(ctx, P, rnd):
    """Wide pleated kasa: radial ribs from the apex, a folded brim break and a rolled rim (the reference hat)."""
    S = ctx.socket
    n, R = int(P['ribs']), P['radius']
    apex, zr = S.z + P['rise'], S.z + P['brim_lift']
    rings = [poly_ring(n, R * 0.05, apex, flute=0.0),
             poly_ring(n, R * 0.58, apex - (apex - zr) * 0.58, flute=0.085, lift=0.009),
             poly_ring(n, R, zr, flute=0.105, lift=0.016)]
    bm = bmesh.new()
    skin_rings(bm, rings, cap_first=True)
    kasa = ctx.add('kasa', bm, [ctx.mat(P.get('material', 'washi_hat')), ctx.mat('washi_shade')],
                   thickness=0.0045)
    # rolled rim: a low-poly ring of card folded back on itself, the crisp line the reference ends on
    rim = bmesh.new()
    skin_rings(rim, [poly_ring(n, R, zr + P['rim_roll'] * 0.5, flute=0.105, lift=0.016),
                     poly_ring(n, R + P['rim_roll'], zr, flute=0.02),
                     poly_ring(n, R, zr - P['rim_roll'] * 0.9, flute=0.105, lift=0.016)])
    ctx.add('kasa_rim', rim, [ctx.mat('washi_shade'), ctx.mat('seam_shadow')], thickness=0.0028)
    # the shadow under the brim, so the mask sits in a dark cave like the reference
    ring = bmesh.new()
    skin_rings(ring, [poly_ring(n, R * 0.26, zr + 0.075, flute=0.0),
                      poly_ring(n, R * 0.94, zr + 0.004, flute=0.08)])
    ctx.add('kasa_under', ring, [ctx.mat('seam_shadow')], thickness=0.002, rim_mat=False)
    return kasa


@part('kasa_narrow', slot='hat', socket='head_top', bone='head', size=(0.85, 1.15), material='washi_hat',
      ribs=16, radius=0.29, rise=0.235, brim_lift=0.085, rim_roll=0.011, proportions=('slim', 'standard'))
def kasa_narrow(ctx, P, rnd):
    """Narrow travelling kasa: fewer, deeper ribs and a tight rim — reads in a close-up without hiding the face."""
    return kasa_wide(ctx, P, rnd)


@part('hachigane', slot='hat', socket='head_top', bone='head', size=(0.9, 1.1), material='card_charcoal',
      width=0.115, height=0.055, spine=True, proportions=('standard', 'broad'), tags=('armour',))
def hachigane(ctx, P, rnd):
    """Folded iron-card brow band with a centre spine: the armoured head, no hat.
    `material` colours the band and `spine: false` drops the iron plate, which makes the same part a plain
    cloth headband (hachimaki) - Musashi's white band at Ganryujima (research/ganryujima.md) - from data."""
    S = ctx.socket
    z = S.z - 0.085
    pts, faces = [], []
    n = 9
    for i in range(n):
        a = math.pi * (i / (n - 1)) + math.pi * 0.5
        x, y = P['width'] * math.cos(a), P['width'] * 0.92 * math.sin(a)
        pts += [(x, y, z), (x, y, z + P['height'] * (1.0 if i in (3, 4, 5) else 0.72))]
    for i in range(n - 1):
        faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
    band = ctx.add('hachigane', shell(pts, faces), [ctx.mat(P.get('material', 'card_charcoal')), ctx.mat('seam_shadow')],
                   thickness=0.008)
    if P['spine']:
        ctx.add('hachigane_spine', box(0, -P['width'] * 0.90, z + P['height'] * 0.55, 0.018, 0.03, 0.075,
                                       rot=(0.3, 0, 0)), [ctx.mat(P.get('material', 'card_charcoal')), ctx.mat('seam_shadow')],
                thickness=0.006)
    return band


@part('mask_angular', slot='face', socket='face', bone='head', size=(0.9, 1.12), material='washi_natural',
      length=0.205, width=0.134, ridge=0.046, slit=0.014, tags=('reference',),
      proportions=('slim', 'standard', 'broad'))
def mask_angular(ctx, P, rnd):
    """Angular folded face: a nose ridge down the centre, flat cheek planes, a cut chin and two eye slits."""
    S = ctx.socket
    w, L, r = P['width'], P['length'], P['ridge']
    top, mid, chin = S.z + L * 0.42, S.z + L * 0.02, S.z - L * 0.58
    # 0 crown, 1/2 brow sides, 3 nose bridge, 4/5 cheek sides, 6 nose tip, 7/8 jaw, 9 chin, 10/11 back
    P3 = [(0, 0.02, top + 0.02),
          (w * 0.92, 0.015, top - 0.015), (-w * 0.92, 0.015, top - 0.015),
          (0, -r * 0.85, top - 0.045),
          (w * 0.96, -0.018, mid), (-w * 0.96, -0.018, mid),
          (0, -r, mid - 0.015),
          (w * 0.62, -0.012, chin + 0.055), (-w * 0.62, -0.012, chin + 0.055),
          (0, -r * 0.68, chin),
          (w * 0.52, 0.085, top - 0.03), (-w * 0.52, 0.085, top - 0.03),
          (w * 0.40, 0.075, chin + 0.03), (-w * 0.40, 0.075, chin + 0.03),
          (0, 0.085, chin + 0.02)]
    F = [(0, 3, 1), (0, 2, 3), (1, 3, 6, 4), (2, 5, 6, 3), (4, 6, 9, 7), (5, 8, 9, 6),
         (7, 9, 14, 12), (8, 13, 14, 9), (0, 1, 10), (0, 11, 2), (1, 4, 12, 10), (2, 11, 13, 5),
         (4, 7, 12), (5, 13, 8), (10, 12, 14, 11), (11, 14, 13)]
    bm = shell(P3, F)
    creases(bm, inset=0.0035, depth=-0.0018, share=0.55, rnd=rnd)
    face = ctx.add('face_mask', bm, [ctx.mat(P.get('material', 'washi_natural'), glow=True), ctx.mat('washi_shade')],
                   thickness=0.0075)
    # eye slits: a cut through the sheet, the lantern burning out of it
    for sgn in (1, -1):
        ctx.add(f'eye_{"L" if sgn > 0 else "R"}',
                box(sgn * w * 0.46, -r * 0.86, mid + 0.052, 0.062, 0.016, P['slit'],
                    rot=(0, sgn * 0.26, sgn * -0.22)), [ctx.emit('eye', 26.0)], thickness=0.0)
        # the cut: a dark slot behind the slit, so the eye is a HOLE in the sheet, not a painted mark
        ctx.add(f'eye_slot_{"L" if sgn > 0 else "R"}',
                box(sgn * w * 0.46, -r * 0.58, mid + 0.052, 0.076, 0.030, P['slit'] * 2.4,
                    rot=(0, sgn * 0.26, sgn * -0.22)), [ctx.mat('seam_shadow')], thickness=0.0)
        # a crease running from the eye slit down to the jaw, the way a folded mask is scored
        ctx.add(f'eye_crease_{"L" if sgn > 0 else "R"}',
                box(sgn * w * 0.60, -r * 0.80, chin + 0.095, 0.010, 0.012, 0.115,
                    rot=(0, sgn * 0.30, sgn * 0.10)), [ctx.mat('seam_shadow')], thickness=0.0)
    return face


@part('mask_long', slot='face', socket='face', bone='head', size=(0.9, 1.12), material='washi_bleached',
      length=0.235, width=0.112, ridge=0.052, slit=0.012, proportions=('slim', 'standard'))
def mask_long(ctx, P, rnd):
    """A longer, narrower mask with a deeper nose ridge: the gaunt ronin read."""
    return mask_angular(ctx, P, rnd)


@part('hair_spikes', slot='hair', socket='hair_back', bone='head', size=(0.85, 1.15), material='washi_shade',
      blades=5, length=0.17, proportions=('slim', 'standard', 'broad'))
def hair_spikes(ctx, P, rnd):
    """Folded hair: flat paper blades fanning back off the crown, each one a single crease."""
    S = ctx.socket
    bm = bmesh.new()
    for k in range(int(P['blades'])):
        a = (k - (P['blades'] - 1) / 2) * 0.42
        L = P['length'] * (1.0 - 0.13 * abs(k - (P['blades'] - 1) / 2))
        root = Vector((math.sin(a) * 0.065, S.y - 0.01, S.z + 0.025))
        tip = root + Vector((math.sin(a) * 0.5, 0.80, -0.30)).normalized() * L
        w = 0.026
        side = Vector((math.cos(a), -math.sin(a) * 0.3, 0)) * w
        up = Vector((0, 0.25, 0.9)).normalized() * w * 0.8
        join(bm, shell([tuple(root - side), tuple(root + side), tuple(tip), tuple(root + up)],
                       [(0, 1, 2), (0, 2, 3), (1, 3, 2), (0, 3, 1)]))
    return ctx.add('hair', bm, [ctx.mat('washi_shade'), ctx.mat('seam_shadow')], thickness=0.004)


@part('topknot', slot='hair', socket='hair_back', bone='head', size=(0.85, 1.15), material='card_indigo',
      length=0.13, proportions=('standard', 'broad'), tags=('armour',))
def topknot(ctx, P, rnd):
    """A tight folded chonmage: a rolled card cylinder lying forward over the crown."""
    S = ctx.socket
    bm = bmesh.new()
    skin_rings(bm, [poly_ring(6, 0.030, 0, cx=0, cy=0), poly_ring(6, 0.034, P['length'] * 0.55),
                    poly_ring(6, 0.022, P['length'])], cap_first=True, cap_last=True)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-1.15, 3, 'X'))
    bmesh.ops.translate(bm, vec=(0, S.y - 0.02, S.z + 0.045), verts=bm.verts)
    return ctx.add('topknot', bm, [ctx.mat('card_indigo'), ctx.mat('seam_shadow')], thickness=0.005)


@part('neck_column', slot='neck', socket='neck', bone='neck', size=(0.9, 1.1), material='washi_shade',
      radius=0.050, proportions=('slim', 'standard', 'broad'))
def neck_column(ctx, P, rnd):
    """The folded neck: a short five-sided column, deliberately dark so the collar gap glows around it."""
    S = ctx.socket
    bm = bmesh.new()
    skin_rings(bm, [poly_ring(5, P['radius'] * 1.12, S.z - 0.06), poly_ring(5, P['radius'], S.z + 0.055)])
    return ctx.add('neck', bm, [ctx.mat('washi_shade', glow=True), ctx.mat('seam_shadow')], thickness=0.005)


# =========================================================================== the folded-sheet frame
# The body is built from FEW, BIG sheets that LAYER over each other. Everything below shares three "frames"
# (the kimono wrap, the sleeve cone, the hakama leg cone) so that separate parts — torso and lapels, upper
# sleeve and hanging bag, thigh and shin — are cut from the same lines and step over each other cleanly.
def lerp3(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def asset_bmesh(path, *, target_faces=900, scale=1.0, align='socket', socket=None):
    """Load a bought or generated mesh (GLB/FBX/OBJ) and hand back a bmesh the part pipeline can use.

    This is the bridge between a 3D-generation service and this character factory. A service - Tripo,
    Meshy, Rodin, a local Hunyuan3D-Part - returns a mesh. What this project needs is a PART: one
    object, at a socket, on a bone, made of paper. Everything after this call does that, because the
    mesh goes through exactly the same `ctx.add()` as a hand-folded part and gets the same flat
    facets, the same per-facet tone, the same cut-paper thickness and the same washi material.

    So the division of labour is: buy the geometry, keep the skeleton. A generated mesh is one fused
    shell when it is a whole character, which is why rig_trellis.py was abandoned - but one PART is
    a legitimate fused shell, because a hat does not bend. Buy hats, masks, helmets, armour plates,
    weapons and props. Fold the kimono, the hakama and the sleeves here, where they have to deform.

    target_faces matters more than it looks. A generated mesh arrives at 30-80k smooth triangles; a
    folded paper part is a few hundred flat ones. Decimating hard is not a compromise, it is the
    style: the planes have to be big enough to read as folds.
    """
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext == '.glb' or ext == '.gltf':
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f'asset_bmesh: {path}: want .glb, .gltf, .fbx or .obj')
    new_objs = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new_objs if o.type == 'MESH']
    if not meshes:
        for o in new_objs:
            bpy.data.objects.remove(o, do_unlink=True)
        raise ValueError(f'asset_bmesh: {path} contained no mesh')

    # Gather every imported mesh into one object, in world space. The decimation has to happen on an
    # OBJECT: bmesh has no decimate operator, only the modifier does a collapse properly.
    work = bpy.data.meshes.new('_asset_work')
    bm0 = bmesh.new()
    for o in meshes:
        me = o.to_mesh()
        tmp = bmesh.new()
        tmp.from_mesh(me)
        bmesh.ops.transform(tmp, matrix=o.matrix_world, verts=tmp.verts[:])
        tmp.to_mesh(me)
        bm0.from_mesh(me)
        tmp.free()
        o.to_mesh_clear()
    bm0.to_mesh(work)
    bm0.free()
    for o in new_objs:                       # the import is a means, not a result
        bpy.data.objects.remove(o, do_unlink=True)

    wob = bpy.data.objects.new('_asset_work', work)
    bpy.context.scene.collection.objects.link(wob)
    n0 = len(work.polygons)
    if target_faces and n0 > target_faces:
        pl = wob.modifiers.new('planar', 'DECIMATE')
        pl.decimate_type = 'DISSOLVE'        # merge coplanar faces: free, and exactly what paper wants
        pl.angle_limit = math.radians(5)
        co = wob.modifiers.new('collapse', 'DECIMATE')
        co.ratio = max(0.02, target_faces / n0)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = wob.evaluated_get(dg)
        baked = bpy.data.meshes.new_from_object(ev)
        wob.modifiers.clear()
        wob.data = baked
        bpy.data.meshes.remove(work)
        work = baked

    bm = bmesh.new()
    bm.from_mesh(work)
    bpy.data.objects.remove(wob, do_unlink=True)
    bpy.data.meshes.remove(work)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    print(f'[asset] {os.path.basename(path)}: {n0} faces -> {len(bm.faces)}')

    # Normalise: drop it on its own origin, scale to `scale` metres tall, then move to the socket.
    vs = bm.verts[:]
    if vs:
        xs = [v.co for v in vs]
        lo = Vector((min(c.x for c in xs), min(c.y for c in xs), min(c.z for c in xs)))
        hi = Vector((max(c.x for c in xs), max(c.y for c in xs), max(c.z for c in xs)))
        mid = (lo + hi) / 2
        height = max(1e-6, hi.z - lo.z)
        k = scale / height if scale else 1.0
        base = Vector((mid.x, mid.y, lo.z if align == 'socket' else mid.z))
        for v in vs:
            v.co = (v.co - base) * k
        if socket is not None:
            for v in vs:
                v.co += Vector(socket)
    tidy(bm)
    return bm


def asset_part(name, *, slot, socket, file, height, bone=None, bones=None, rigid=True,
               material='washi_natural', target_faces=900, align='socket', **kw):
    """Register a file on disk as a PART, with a socket, a bone, a material and a scale range.

    Use it for anything bought or generated that does not have to fold:

        asset_part('kasa_bought', slot='hat', socket='head_top', bone='head',
                   file='assets/models/kasa_hat.glb', height=0.22, material='washi_hat')

    After this it is a part like any other: a recipe names it, the validator checks it, the rig
    drives it, and `ctx.add()` makes it paper. No code in blender/ changes when a new one arrives,
    which is the whole point of the factory.
    """
    @part(name, slot=slot, socket=socket, bone=bone, bones=bones, rigid=rigid,
          material=material, file=file, height=height, target_faces=target_faces,
          align=align, tags=('asset',), **kw)
    def _built(ctx, P, rnd):
        path = P['file']
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), path)
        bm = asset_bmesh(path, target_faces=P['target_faces'], scale=P['height'],
                         align=P['align'], socket=ctx.socket)
        return ctx.add(name, bm, [ctx.mat(P.get('material', material), glow=ctx.lit(0.06)),
                                  ctx.mat('washi_shade')], thickness=0.008)
    return _built


def tidy(bm):
    """Consistent normals: solidify needs every face of a sheet to agree which side is 'out'."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def pw(z, table):
    """Piecewise-linear lookup in [(z, value), ...] sorted by z."""
    if z <= table[0][0]:
        return table[0][1]
    for (z0, v0), (z1, v1) in zip(table, table[1:]):
        if z <= z1:
            return v0 + (v1 - v0) * (z - z0) / (z1 - z0)
    return table[-1][1]


def outline_ring(outline, z, hw, hd, cx=0.0, cy=0.0):
    return [(cx + u * hw, cy + v * hd, z) for u, v in outline]


# --------------------------------------------------------------------------- kimono wrap frame
CORE_OUTLINE = [(-0.62, -1.0), (0.62, -1.0), (1.0, -0.40), (1.0, 0.45), (0.55, 1.0), (0.0, 1.13),
                (-0.55, 1.0), (-1.0, 0.45), (-1.0, -0.40)]
CORE_HD = [(0.90, 0.082), (1.00, 0.085), (1.28, 0.100), (1.36, 0.098), (1.445, 0.078)]
SHEET_TUCK = 0.985            # the front sheets run down to here, hidden under the obi
OBI_Z = (0.925, 1.050)
OBI_HW, OBI_HD = 0.168, 0.137


def core_front(z):
    return -pw(z, CORE_HD)


def kimono_sheet(sg, over, shoulder=0.268, step=0.024):
    """One front sheet of the wrap. sg=+1 is the wearer's LEFT sheet. `over` puts it a full step proud.
    Named points: ridge at neck/shoulder (Rn, Rs), front shoulder edge (Fn, Fs), armpit (C), side waist (D),
    the fold point on the diagonal (M) and the far waist where the diagonal tucks under the obi (E)."""
    sh = shoulder
    off = 0.012 + (step if over else 0.0)
    K = dict(
        Rn=(sg * 0.075, 0.005, 1.468), Rs=(sg * sh, 0.005, 1.405),
        Fn=(sg * 0.075, -0.080, 1.445), Fs=(sg * sh, -0.098, 1.385),
        Bn=(sg * 0.075, 0.090, 1.445), Bs=(sg * sh, 0.098, 1.385),
        C=(sg * (sh - 0.066), -0.120, 1.250),
        D=(sg * 0.153, -0.098 if over else -0.088, SHEET_TUCK),
        M=(sg * 0.001, core_front(1.28) - off, 1.28),
        E=(-sg * 0.125, core_front(SHEET_TUCK) - off if over else -0.066, SHEET_TUCK),
        Bs2=(sg * (sh - 0.050), 0.122, 1.250),
        Bc2=(-sg * 0.016 if over else 0.0, 0.138 if over else 0.128, 1.250),
        Bc=(-sg * 0.016 if over else 0.0, 0.114 if over else 0.104, 1.440),
        LF=(sg * (sh + 0.006), -0.094, 1.340), LR=(sg * (sh + 0.006), 0.005, 1.362),
        LB=(sg * (sh + 0.006), 0.096, 1.340))
    return K


# --------------------------------------------------------------------------- sleeve cone frame
# Six ridge lines fan from the shoulder to a wide, slanted mouth. Offsets are from the shoulder socket, +x
# outboard. Order: inner-front, front, outer-front, outer-back, back (the low folded corner), inner-back.
SLV_TOP = [(-0.065, -0.064, -0.022), (-0.005, -0.078, -0.030), (0.028, -0.064, -0.042),
           (0.028, 0.072, -0.042), (-0.005, 0.090, -0.030), (-0.065, 0.072, -0.022)]
SLV_MOUTH = [(-0.075, -0.085, -0.360), (0.060, -0.160, -0.400), (0.190, -0.110, -0.470),
             (0.210, 0.100, -0.560), (0.090, 0.180, -0.610), (-0.075, 0.100, -0.520)]


def sleeve_point(i, t, S, sg, spread=1.0, off=0.0):
    a, b = SLV_TOP[i], SLV_MOUTH[i]
    b = (-0.010 + (b[0] + 0.010) * spread, b[1] * (0.55 + 0.45 * spread), b[2])
    p = lerp3(a, b, t)
    if off:
        cs = [lerp3(SLV_TOP[k], SLV_MOUTH[k], t) for k in range(6)]
        cx, cy = sum(c[0] for c in cs) / 6, sum(c[1] for c in cs) / 6
        d = math.hypot(p[0] - cx, p[1] - cy) or 1.0
        p = (p[0] + (p[0] - cx) / d * off, p[1] + (p[1] - cy) / d * off, p[2])
    return (S.x + sg * p[0], S.y + p[1], S.z + p[2])


def sleeve_ring(ts, S, sg, spread=1.0, off=0.0, valley=0.020):
    """One ring of the sleeve cone. `ts` is one t or six (a slanted cut). Between the three outboard ridges
    a VALLEY crease is folded in, deepening toward the mouth: the same mountain/valley language as the kasa."""
    ts = [ts] * 6 if isinstance(ts, (int, float)) else list(ts)
    R = [Vector(sleeve_point(i, ts[i], S, sg, spread, off)) for i in range(6)]
    c = sum(R, Vector()) / 6
    out = []
    for i in range(6):
        out.append(tuple(R[i]))
        if i in (1, 2, 3) and valley:
            m = (R[i] + R[i + 1]) / 2
            d = Vector((c.x - m.x, c.y - m.y, 0.0))
            tm = (ts[i] + ts[i + 1]) / 2
            m = m + d.normalized() * valley * tm * spread + Vector((0, 0, 0.012 * tm))
            out.append(tuple(m))
    return out


# --------------------------------------------------------------------------- hakama leg cone frame
LEG_TOP, LEG_HEM = 0.968, 0.072


def leg_outline(pd, pleats=3, back_pleats=2):
    """Cross-section of one hakama leg, u 0→1 inner→outer, v -1→1 front→back. The front is KNIFE PLEATS:
    each panel starts proud at a sharp ridge and slopes back to a valley, then steps forward to the next
    ridge — stacked sheets with a real step, ridges pointing at the centre split like a real hakama.

    The BACK is pleated too, which it was not before. A real hakama carries five pleats in front and two
    behind; this had three in front and a plain four-point sweep behind. The cost was not subtle: a
    turnaround showed the legs as two smooth tubes from the back, and the side view lost its folds
    entirely, because at 90 degrees you are looking at the unpleated flank of a front-only pleat. The
    camera that is on screen longest in this project is `orbit`, which circles the character, so those
    were the two angles it looked at most (docs/PHASE1-VERDICT.md).
    """
    n = int(pleats)
    xs = [k / n for k in range(n + 1)]
    pts = []
    for k in range(n):
        pts.append((xs[k] - (0.03 if k else 0.0), -0.90 + 0.10 * xs[k] - pd))      # ridge
        pts.append((xs[k + 1], -0.90 + 0.10 * xs[k + 1]))                           # valley
    pts.append((1.06, 0.0))                                                         # the outer flank

    # Back pleats, built the same way round: step u from the outer flank back to the centre seam, and
    # ride the same envelope the four plain points used to describe (1.0→0.74, 0.55→0.98, 0.0→0.80),
    # lifting each ridge proud of it by the same pleat depth the front uses so both halves read alike.
    b = max(1, int(back_pleats))
    env = lambda u: (0.74 + (0.98 - 0.74) * (1.0 - u) / 0.45 if u >= 0.55
                     else 0.98 - (0.98 - 0.80) * (0.55 - u) / 0.55)
    for k in range(b):
        u0 = 1.0 - k / b
        u1 = 1.0 - (k + 1) / b
        pts.append((u0, env(u0) + pd * 0.55))                                       # ridge, standing proud
        pts.append((u1 + (0.03 if k < b - 1 else 0.0), env(u1)))                     # valley, stepped in
    return pts


def leg_point(u, v, z, sg, P, extra=0.0):
    s = min(max((LEG_TOP - z) / (LEG_TOP - LEG_HEM), 0.0), 1.0)
    kick = max(0.0, (s - 0.84) / 0.16) * P.get('kick', 0.02)
    xi = 0.004 + P.get('split', 0.046) * s ** 1.3 - extra * 0.4
    xo = 0.150 + (P.get('hem', 0.250) - 0.150) * s + kick + extra
    hd = 0.112 + 0.022 * s + kick + extra
    return (sg * (xi + u * (xo - xi)), v * hd, z)


def leg_ring(z, sg, P, extra=0.0, zfn=None):
    s = min(max((LEG_TOP - z) / (LEG_TOP - LEG_HEM), 0.0), 1.0)
    out = []
    for u, v in leg_outline(P.get('pleat', 0.22) * (0.25 + 0.75 * s), P.get('pleats', 3)):
        zz = zfn(u, v) if zfn else z
        out.append(leg_point(u, v, zz, sg, P, extra))
    return out


# =========================================================================== PARTS: body
@part('kimono_layered', slot='torso', socket='chest', bone='torso', bones=['torso', 'upper'], rigid=False,
      size=(0.9, 1.15), material='washi_natural', shoulder=0.268, chest=0.158, waist=0.132, step=0.024,
      tags=('reference',), proportions=('slim', 'standard', 'broad'))
def kimono_layered(ctx, P, rnd):
    """Wrapped kimono: ONE big diagonal sheet (left over right) across the chest, a second sheet crossing under it, both folded over the shoulders into a back yoke and tucked under the obi."""
    main = P.get('material', 'washi_natural')
    wz = [(0.90, P['waist'] * 0.97), (1.00, P['waist']), (1.20, P['chest']), (1.36, P['chest'] * 1.09),
          (1.415, P['chest'] * 1.04)]
    bm = bmesh.new()
    rings = [outline_ring(CORE_OUTLINE, z, hw, pw(z, CORE_HD)) for z, hw in wz]
    rings.append(outline_ring(CORE_OUTLINE, 1.452, 0.062, 0.060))
    skin_rings(bm, rings, cap_last=True)
    # The core shows below the free lower edge of the back yoke. Pale shade under a pale robe is right; under a
    # COLOURED robe it read as a white panel in the middle of the back, so a coloured robe colours its core
    # too (`core` overrides either way).
    core = P.get('core', 'washi_shade' if main == 'washi_natural' else main)
    body = ctx.add('kimono_body', tidy(bm), [ctx.mat(core, glow=ctx.lit(0.15)), ctx.mat('seam_shadow')],
                   thickness=0.008)
    # the glowing core seen through the collar gap and the sleeve mouths
    ctx.add('inner_lantern', box(0, 0.0, 1.20, 0.09, 0.06, 0.34), [ctx.emit('core', 2.6)],
            thickness=0.0, to_camera=False)
    # Centre back seam (背縫い). A kimono is two panels joined down the spine, and that join is a
    # real fold that catches light. Without it the whole upper back renders as one smooth slab,
    # which is exactly what the turnaround test showed (docs/PHASE1-VERDICT.md): the front read as
    # folded paper and the back read as a pillowcase. CORE_OUTLINE's (0.0, 1.13) is the back centre,
    # so the ridge sits at x = 0, y = 1.13 x half-depth, standing a few millimetres proud.
    sz = [1.05, 1.16, 1.27, 1.37, 1.425]
    halfw, proud = 0.018, 0.0065
    spts, sfaces = [], []
    for z in sz:
        back = 1.13 * pw(z, CORE_HD)
        spts += [(-halfw, back, z), (0.0, back + proud, z), (halfw, back, z)]
    for i in range(len(sz) - 1):
        a, b = i * 3, (i + 1) * 3
        sfaces += [(a, a + 1, b + 1, b), (a + 1, a + 2, b + 2, b + 1)]
    ctx.add('kimono_back_seam', shell(spts, sfaces),
            [ctx.mat(main), ctx.mat('seam_shadow')], thickness=0.004)

    # juban: the under-robe showing in the V of the collar, set well back so the neck sits in a real recess
    ctx.add('juban', shell([(0.070, -0.058, 1.458), (-0.070, -0.058, 1.458), (0.0, -0.088, 1.285)],
                           [(0, 1, 2)]),
            [ctx.mat('washi_bleached', glow=ctx.lit(0.35)), ctx.mat('seam_shadow')], thickness=0.006)
    for tag, sg, over in (('under', -1, False), ('over', 1, True)):
        K = kimono_sheet(sg, over, P['shoulder'], P['step'])
        names = ['Rn', 'Rs', 'Fn', 'Fs', 'Bn', 'Bs', 'C', 'D', 'M', 'E', 'Bs2', 'Bc2', 'Bc', 'LF', 'LR', 'LB']
        ix = {n: i for i, n in enumerate(names)}
        F = [('Rn', 'Rs', 'Fs', 'Fn'),            # shoulder top, front half: the big flat shoulder plane
             ('Rn', 'Bn', 'Bs', 'Rs'),            # shoulder top, back half
             ('Fn', 'Fs', 'M'),                   # chest plane running to the diagonal
             ('Fs', 'C', 'M'),                    # the fold from the shoulder tip to the sternum
             ('C', 'D', 'E', 'M'),                # the wrap down to the waist, tucked under the obi
             ('Bn', 'Bc2', 'Bs2', 'Bs'), ('Bn', 'Bc', 'Bc2'),      # back yoke with a free lower edge
             ('Fs', 'Rs', 'LR', 'LF'), ('Rs', 'Bs', 'LB', 'LR')]   # the lip folded down over the sleeve head
        bm = shell([K[n] for n in names], [[ix[n] for n in f] for f in F])
        if over:                                   # the dark slot behind the overlap, flush on the under sheet
            U = kimono_sheet(-1, False, P['shoulder'], P['step'])
            m, e = Vector(K['M']), Vector(K['E'])
            um = Vector((0.0, U['M'][1] - 0.007, 1.28))
            ue = Vector((e.x, core_front(SHEET_TUCK) - 0.020, e.z))
            slot = [um + Vector((-0.004, 0, 0.008)), um + Vector((0.040, 0, -0.010)),
                    ue + Vector((0.045, 0, 0)), ue + Vector((-0.004, 0, 0))]
            ctx.add('kimono_seam', panel([tuple(p) for p in slot]), [ctx.mat('seam_shadow')],
                    thickness=0.0015, rim_mat=False)
        mats = [ctx.mat(main if over else P.get('under', 'washi_bleached')), ctx.mat('washi_shade')]
        if not over:
            # The under sheet is the pale under-layer only at the FRONT (the V and below the overlap). Its back
            # yoke is the other half of the same outer garment, so it takes the outer colour: coloured whole,
            # every coloured costume read half colour, half white from behind (Kojiro and Musashi turnarounds,
            # Nov 26). Slots 2-3 repeat the pair so the solidify rim offset (+1) still lands on washi_shade.
            back = {ix[n] for n in ('Bn', 'Bs', 'Bc', 'Bc2', 'Bs2', 'LB')}
            bm.verts.index_update()
            for f in bm.faces:
                if {v.index for v in f.verts} & back:
                    f.material_index = 2
            mats += [ctx.mat(main), ctx.mat('washi_shade')]
        ctx.add(f'kimono_{tag}', tidy(bm), mats, thickness=0.010)
    return body


@part('kimono_plain', slot='torso', socket='chest', bone='torso', bones=['torso', 'upper'], rigid=False,
      size=(0.9, 1.15), material='card_indigo', shoulder=0.285, chest=0.165, waist=0.134, step=0.020,
      proportions=('standard', 'broad'), tags=('armour',))
def kimono_plain(ctx, P, rnd):
    """A broader under-kimono of heavy card, the same wrap with wider shoulder planes: the body an armoured warrior straps plates onto."""
    return kimono_layered(ctx, P, rnd)


@part('eri_crossed', slot='collar', socket='collar', bone='upper', bones=['torso', 'upper'], rigid=False,
      size=(0.9, 1.12), material='washi_bleached', width=0.052, stand=0.050, tags=('reference',),
      proportions=('slim', 'standard', 'broad'))
def eri_crossed(ctx, P, rnd):
    """Crossed lapels, LEFT OVER RIGHT: a folded band riding proud along each diagonal, running up into a standing collar that steps clear of the neck (outer collar + inner juban collar)."""
    w = P['width']
    sheet = P.get('material', 'washi_bleached')
    made = None
    for tag, sg, over in (('under', -1, False), ('over', 1, True)):
        K = kimono_sheet(sg, over)
        fn, m, e = Vector(K['Fn']), Vector(K['M']), Vector(K['E'])
        if not over:                               # the under lapel dies away just past the crossing
            e = m + (Vector((sg * -0.125, m.y + 0.012, SHEET_TUCK)) - m) * 0.12
        d = Vector((e.x - fn.x, 0, e.z - fn.z)).normalized()
        nrm = Vector((d.z, 0, -d.x)) * sg          # in the front plane, pointing at the open V
        if nrm.z < 0:
            nrm = -nrm
        proud = 0.013 if over else 0.010
        top = fn + Vector((-sg * 0.010, 0.012, 0.016))          # the band starts up at the collar stand
        st = [(top, 0.004), (m, -0.003), (e, 0.004)]             # (edge point, how much the far edge sits back)
        pts = []
        for k, (p, back) in enumerate(st):
            pr = proud if k < 2 else proud - 0.022            # the last station dives under the obi
            free = p + nrm * 0.008 + Vector((0, -pr, 0))
            ridge = p - nrm * (w * 0.42) + Vector((0, -pr - (0.009 if k < 2 else 0.0), 0))
            inner = p - nrm * w + Vector((0, -pr + back, 0))
            pts += [tuple(free), tuple(ridge), tuple(inner)]
        F = [(0, 1, 4, 3), (1, 2, 5, 4), (3, 4, 7, 6), (4, 5, 8, 7)]
        made = ctx.add(f'eri_{tag}', tidy(shell(pts, F)),
                       [ctx.mat(sheet if over else 'washi_shade'), ctx.mat('washi_shade')],
                       thickness=0.008 if over else 0.006)
    # the standing collar: two concentric folded bands open at the front. The gap between the inner band and
    # the neck column is the neck shadow slot; the step between the two bands is the collar step.
    for tag, r, ry, h, lean, key in (('stand', 0.088, 0.100, P['stand'], 0.012, sheet),
                                     ('inner', 0.068, 0.078, P['stand'] + 0.014, 0.004, 'washi_natural')):
        lo, hi = [], []
        n = 9
        for i in range(n):
            a = math.radians(-58 + (296 * i / (n - 1)))
            c, s = math.cos(a), math.sin(a)
            zb = 1.446 + 0.018 * abs(c)
            lo.append((r * c, 0.012 + ry * s, zb - 0.012))
            rise = 0.22 + 0.78 * min(max((s + 0.85) / 1.1, 0.0), 1.0)      # low at the lapels, full at the nape
            hi.append(((r + lean) * c, 0.012 + (ry + lean * 1.3) * s, zb + h * rise * (1.0 + 0.3 * max(s, 0))))
        bm = bmesh.new()
        skin_rings(bm, [lo, hi], close=False)
        ctx.add(f'eri_{tag}', tidy(bm), [ctx.mat(key), ctx.mat('washi_shade')], thickness=0.008)
    return made


@part('eri_narrow', slot='collar', socket='collar', bone='upper', bones=['torso', 'upper'], rigid=False,
      size=(0.9, 1.12), material='card_indigo', width=0.034, stand=0.034, proportions=('standard', 'broad'),
      tags=('armour',))
def eri_narrow(ctx, P, rnd):
    """A narrow dark collar that disappears under armour, still crossed left over right."""
    return eri_crossed(ctx, dict(P, material='card_indigo'), rnd)


OBI_OUTLINE = [(-0.60, -1.0), (0.60, -1.0), (1.0, -0.42), (1.0, 0.42), (0.60, 1.0), (-0.60, 1.0),
               (-1.0, 0.42), (-1.0, -0.42)]


@part('obi_knot', slot='obi', socket='obi', bone='torso', size=(0.9, 1.1), material='washi_shade',
      height=0.125, knot=0.085, cord=True, tags=('reference',), proportions=('slim', 'standard', 'broad'))
def obi_knot(ctx, P, rnd):
    """The sash: a wide flat band standing proud of the robe (the sheets tuck under it), a second diagonal pass over it, a folded knot with two tails, and a thin cord."""
    h = P['height']
    z0 = OBI_Z[0]
    bm = bmesh.new()
    skin_rings(bm, [outline_ring(OBI_OUTLINE, z0, OBI_HW, OBI_HD),
                    outline_ring(OBI_OUTLINE, z0 + h, OBI_HW, OBI_HD)])
    band = ctx.add('obi', tidy(bm), [ctx.mat('washi_shade'), ctx.mat('seam_shadow')], thickness=0.012)
    # the second pass of the strip: narrower and a full step proud, so the sash reads as stacked paper
    bm2 = bmesh.new()
    skin_rings(bm2, [outline_ring(OBI_OUTLINE, z0 + h * 0.24, OBI_HW + 0.013, OBI_HD + 0.013),
                     outline_ring(OBI_OUTLINE, z0 + h * 0.76, OBI_HW + 0.013, OBI_HD + 0.013)])
    ctx.add('obi_wrap2', tidy(bm2), [ctx.mat('washi_natural'), ctx.mat('seam_shadow')], thickness=0.010)
    # the knot: a flat folded diamond on the front-left, with two tails folded out from under it
    k = P['knot']
    yk = -OBI_HD - 0.026
    xk, zk = 0.075, z0 + h * 0.50
    ctx.add('obi_knot_tail', tidy(shell(
        [(xk - 0.018, yk + 0.004, zk), (xk + 0.026, yk + 0.004, zk - 0.010),
         (xk + 0.060, yk - 0.012, zk - k * 2.3), (xk + 0.004, yk - 0.012, zk - k * 2.55),
         (xk - 0.030, yk + 0.002, zk - 0.004), (xk + 0.006, yk + 0.002, zk - 0.016),
         (xk - 0.040, yk - 0.004, zk - k * 1.75), (xk - 0.082, yk - 0.004, zk - k * 1.55)],
        [(0, 1, 2, 3), (4, 5, 6, 7)])),
        [ctx.mat('washi_natural'), ctx.mat('seam_shadow')], thickness=0.008)
    # the knot itself: the strip passed once round the sash — a keeper loop standing proud, slightly askew
    yo = -OBI_HD - 0.006
    lp = []
    for dx, lean in ((-k * 0.36, -0.010), (k * 0.36, 0.010)):
        lp += [(xk + dx + lean, yo, z0 + h + 0.012), (xk + dx + lean, yo - 0.030, z0 + h + 0.004),
               (xk + dx - lean, yo - 0.030, z0 - 0.004), (xk + dx - lean, yo, z0 - 0.012)]
    ctx.add('obi_knot', tidy(shell(lp, [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6)])),
            [ctx.mat('washi_shade'), ctx.mat('seam_shadow')], thickness=0.010)
    z0, z1 = OBI_Z[0] + 0.050, OBI_Z[0] + P['height'] + 0.030
    yk = OBI_HD + 0.016
    ctx.add('koshiita', tidy(shell([(-0.090, yk + 0.006, z0), (0.090, yk + 0.006, z0),
                                    (0.058, yk - 0.020, z1), (-0.058, yk - 0.020, z1)], [(0, 1, 2, 3)])),
            [ctx.mat('card_indigo'), ctx.mat('seam_shadow')], thickness=0.012)
    if P['cord']:
        cord = bmesh.new()
        skin_rings(cord, [outline_ring(OBI_OUTLINE, z0 + h * 0.44, OBI_HW + 0.022, OBI_HD + 0.022),
                          outline_ring(OBI_OUTLINE, z0 + h * 0.56, OBI_HW + 0.022, OBI_HD + 0.022)])
        ctx.add('obi_cord', tidy(cord), [ctx.mat('card_indigo'), ctx.mat('seam_shadow')], thickness=0.008)
    return band


@part('obi_plain', slot='obi', socket='obi', bone='torso', size=(0.9, 1.1), material='card_charcoal',
      height=0.095, knot=0.055, cord=False, proportions=('standard', 'broad'), tags=('armour',))
def obi_plain(ctx, P, rnd):
    """A flat battle sash with a small knot and no cord: the armoured warrior's belt."""
    return obi_knot(ctx, P, rnd)


# =========================================================================== PARTS: arms
@part('sleeve_upper_folded', slot='sleeve_upper', socket=['shoulder.L', 'shoulder.R'], bone=None,
      size=(0.9, 1.15), material='washi_natural', spread=1.0, step=0.016,
      proportions=('slim', 'standard', 'broad'))
def sleeve_upper_folded(ctx, P, rnd):
    """Upper sleeve: the top tier of the sleeve cone — six big planes fanning out from under the shoulder sheet, cut off on a diagonal so the hanging bag steps out from beneath it."""
    S, sg = ctx.socket, ctx.side
    cut = [0.40, 0.44, 0.54, 0.60, 0.56, 0.46]            # the diagonal lower edge: high in front, low behind
    top = sleeve_ring(0.0, S, sg, P['spread'], 0.003)
    bot = sleeve_ring([c * (0.6 + 0.4 * P['spread']) for c in cut], S, sg, P['spread'], P['step'])
    bm = bmesh.new()
    skin_rings(bm, [top, bot], cap_first=True)
    return ctx.add(f'sleeve_upper_{"L" if sg > 0 else "R"}', tidy(bm),
                   [ctx.mat(P.get('material', 'washi_natural')), ctx.mat('washi_shade')],
                   thickness=0.010)


@part('kote_narrow', slot='sleeve_upper', socket=['shoulder.L', 'shoulder.R'], bone=None, size=(0.9, 1.1),
      material='card_indigo', spread=0.42, step=0.010, proportions=('standard', 'broad'), tags=('armour',))
def kote_narrow(ctx, P, rnd):
    """A tight armoured sleeve: the same cone with almost no flare, so the shoulder plate reads instead."""
    return sleeve_upper_folded(ctx, P, rnd)


@part('tamoto_wide', slot='sleeve_hanging', socket=['elbow.L', 'elbow.R'], rigid=False,
      bones=['lC', 'lSleeve'], skin='hang', size=(0.85, 1.2), material='washi_bleached',
      spread=1.0, reach=1.0, cuff=0.07, tags=('reference',), proportions=('slim', 'standard', 'broad'))
def tamoto_wide(ctx, P, rnd):
    """The wide hanging sleeve as a SEPARATE folded bag: it flares out and down from under the upper sleeve to a big slanted OPEN mouth with a turned-back cuff and a low folded corner behind."""
    S0, sg = ctx.socket, ctx.side
    S = Vector((S0.x, S0.y, REST['lS'][2]))                # the cone is measured from the shoulder
    sp, reach = P['spread'], P['reach']
    top = sleeve_ring(0.30 * (0.6 + 0.4 * sp), S, sg, sp, -0.014)
    mouth = sleeve_ring(reach, S, sg, sp)
    bm = bmesh.new()
    skin_rings(bm, [top, mouth])
    # the cuff: the mouth edge turned back on itself, a full sheet proud, so the opening has a lip
    c0 = sleeve_ring(reach - P['cuff'], S, sg, sp, 0.011)
    c1 = sleeve_ring(reach + 0.004, S, sg, sp, 0.011)
    skin_rings(bm, [c0, c1])
    ob = ctx.add(f'tamoto_{"L" if sg > 0 else "R"}', tidy(bm),
                 [ctx.mat(P.get('material', 'washi_bleached'), glow=ctx.lit(0.10)), ctx.mat('washi_shade')],
                 thickness=0.009)
    g = sleeve_point(1, reach * 0.9, S, sg, sp)
    ctx.add(f'tamoto_glow_{"L" if sg > 0 else "R"}',
            box(S.x + sg * 0.05 * sp, 0.0, g[2] + 0.05, 0.06 * sp + 0.02, 0.09 * sp + 0.03, 0.012),
            [ctx.emit('sleeve', 2.2)], thickness=0.0, to_camera=False)
    return ob


@part('tamoto_narrow', slot='sleeve_hanging', socket=['elbow.L', 'elbow.R'], rigid=False,
      bones=['lE', 'lS', 'lT'], size=(0.85, 1.2), material='card_indigo',
      spread=0.42, reach=0.66, cuff=0.045, proportions=('standard', 'broad'), tags=('armour',))
def tamoto_narrow(ctx, P, rnd):
    """A short cut-down sleeve for fighting: the same folded bag, tight to the arm and ending above the wrist."""
    return tamoto_wide(ctx, dict(P, material='card_indigo'), rnd)


@part('forearm_folded', slot='forearm', socket=['elbow.L', 'elbow.R'], bone=None, size=(0.9, 1.1),
      material='washi_natural', radius=0.062, proportions=('slim', 'standard', 'broad'))
def forearm_folded(ctx, P, rnd):
    """Forearm sleeve: a narrow folded tube that reaches up INSIDE the hanging sleeve (no gap at the elbow)."""
    S, sg = ctx.socket, ctx.side
    r = P['radius']
    bm = bmesh.new()
    skin_rings(bm, [poly_ring(5, r * 1.00, S.z + 0.100, cx=S.x, phase=0.6),
                    poly_ring(5, r, S.z - 0.14, cx=S.x, phase=0.6),
                    poly_ring(5, r * 0.88, S.z - 0.285, cx=S.x, phase=0.6)])
    return ctx.add(f'forearm_{"L" if sg > 0 else "R"}', bm,
                   [ctx.mat('washi_natural'), ctx.mat('washi_shade')], thickness=0.005)


@part('kote_plated', slot='forearm', socket=['elbow.L', 'elbow.R'], bone=None, size=(0.9, 1.1),
      material='card_charcoal', radius=0.060, plates=3, proportions=('standard', 'broad'), tags=('armour',))
def kote_plated(ctx, P, rnd):
    """Armoured forearm: the folded tube plus three lapped card plates down the outside."""
    S, sg = ctx.socket, ctx.side
    forearm_folded(ctx, P, rnd)
    last = None
    for k in range(int(P['plates'])):
        z = S.z - 0.02 - k * 0.075
        last = ctx.add(f'kote_plate_{k}_{"L" if sg > 0 else "R"}',
                       box(S.x + sg * 0.030, -0.012, z, 0.055, 0.075, 0.062, rot=(0.0, sg * 0.5, 0)),
                       [ctx.mat('card_charcoal'), ctx.mat('seam_shadow')], thickness=0.007)
    return last


@part('hand_folded', slot='hand', socket=['hand.L', 'hand.R'], bone=None, size=(0.9, 1.1),
      material='washi_natural', fingers=4, length=0.095, proportions=('slim', 'standard', 'broad'))
def hand_folded(ctx, P, rnd):
    """Folded-finger hand: ONE sheet — a creased palm with four blades folded out of its lower edge."""
    S, sg = ctx.socket, ctx.side
    x, z = S.x, S.z
    L = P['length']
    # the palm: a single plate, bowed slightly outward, hanging from the wrist
    t0, t1 = (x - sg * 0.010, -0.032, z + 0.028), (x + sg * 0.012, 0.032, z + 0.028)
    b0, b1 = (x - sg * 0.016, -0.038, z - 0.038), (x + sg * 0.016, 0.038, z - 0.038)
    mid = ((t0[0] + t1[0]) / 2 + sg * 0.012, 0.0, (t0[2] + b0[2]) / 2)     # the crease down the palm
    pts = [t0, t1, b1, b0, mid]
    F = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    n = int(P['fingers'])
    for k in range(n):
        u0, u1 = k / n + 0.03, (k + 1) / n - 0.03
        def on_edge(u):
            return tuple(b0[i] + (b1[i] - b0[i]) * u for i in range(3))
        r0, r1 = on_edge(u0), on_edge(u1)
        curl = L * (1.0 - 0.12 * abs(k - (n - 1) / 2))
        tip = (sg * 0.030, 0.0, -curl)
        p0 = tuple(r0[i] + tip[i] for i in range(3))
        p1 = tuple(r1[i] + tip[i] for i in range(3))
        knuckle = (0.5 * (r0[0] + r1[0]) + sg * 0.011, 0.5 * (r0[1] + r1[1]), 0.5 * (r0[2] + r1[2]) - curl * 0.42)
        i = len(pts)
        pts += [r0, r1, p1, p0, knuckle]
        F += [(i, i + 1, i + 4), (i + 1, i + 2, i + 4), (i + 2, i + 3, i + 4), (i + 3, i, i + 4)]
    # the thumb: one more blade folded off the front edge of the palm, laid across
    th0 = (x - sg * 0.004, -0.040, z + 0.006)
    th1 = (x + sg * 0.016, -0.044, z - 0.012)
    th2 = (x + sg * 0.040, -0.052, z - 0.058)
    i = len(pts)
    pts += [th0, th1, th2, (x + sg * 0.030, -0.030, z - 0.050)]
    F += [(i, i + 1, i + 2, i + 3)]
    return ctx.add(f'hand_{"L" if sg > 0 else "R"}', shell(pts, F),
                   [ctx.mat('washi_natural', glow=True), ctx.mat('washi_shade')], thickness=0.005)


# =========================================================================== PARTS: legs
@part('hakama_pleated', slot='thigh', socket=['hip.L', 'hip.R'], rigid=False, bones=['lthigh', 'lshin', 'hips'],
      size=(0.85, 1.2), material='washi_natural', pleats=3, pleat=0.22, hem=0.268, split=0.046, kick=0.028,
      tags=('reference', 'legs'), proportions=('slim', 'standard', 'broad'))
def hakama_pleated(ctx, P, rnd):
    """A REAL hakama leg, upper half: knife pleats fanning from the waist, an open front split against the other leg, cut off on a diagonal a full step proud of the shin sheet below."""
    S, sg = ctx.socket, ctx.side
    rings = [leg_ring(LEG_TOP, sg, P), leg_ring(0.70, sg, P, extra=0.006), leg_ring(0.53, sg, P, extra=0.010),
             leg_ring(0.42, sg, P, extra=0.012),
             leg_ring(0.30, sg, P, extra=0.014, zfn=lambda u, v: 0.335 - 0.06 * min(max(u, 0.0), 1.0))]
    bm = bmesh.new()
    skin_rings(bm, rings)
    return ctx.add(f'hakama_thigh_{"L" if sg > 0 else "R"}', tidy(bm),
                   [ctx.mat(P.get('material', 'washi_natural')), ctx.mat('washi_shade')],
                   thickness=0.009)


@part('hakama_shin_pleated', slot='shin', socket=['knee.L', 'knee.R'], rigid=False, bones=['lthigh', 'lshin', 'hips'],
      size=(0.85, 1.2), material='washi_natural', pleats=3, pleat=0.22, hem=0.268, split=0.046, kick=0.028,
      hem_tilt=0.022, tags=('reference', 'legs'), proportions=('slim', 'standard', 'broad'))
def hakama_shin_pleated(ctx, P, rnd):
    """The hakama leg below the knee: the same pleats running on, kicking out at the hem, which ends in a distinct turned-up hem band."""
    S, sg = ctx.socket, ctx.side
    tilt = lambda u, v: LEG_HEM + P['hem_tilt'] * (v + 1) * 0.5          # front edge low, back edge high
    rings = [leg_ring(0.385, sg, P), leg_ring(0.215, sg, P), leg_ring(LEG_HEM, sg, P, zfn=tilt)]
    bm = bmesh.new()
    skin_rings(bm, rings)
    return ctx.add(f'hakama_shin_{"L" if sg > 0 else "R"}', tidy(bm),
                   [ctx.mat(P.get('material', 'washi_bleached'), glow=ctx.lit(0.08)), ctx.mat('washi_shade')],
                   thickness=0.009)


@part('hakama_plain', slot='thigh', socket=['hip.L', 'hip.R'], rigid=False, bones=['lthigh', 'lshin', 'hips'],
      size=(0.85, 1.2), material='card_indigo', pleats=2, pleat=0.09, hem=0.215, split=0.040, kick=0.0,
      proportions=('standard', 'broad'), tags=('armour', 'legs'))
def hakama_plain(ctx, P, rnd):
    """A plainer, narrower leg of dark card with two shallow pleats: for armour, where deep pleats would fight the plates."""
    return hakama_pleated(ctx, dict(P, material='card_indigo'), rnd)


@part('hakama_shin_plain', slot='shin', socket=['knee.L', 'knee.R'], rigid=False, bones=['lthigh', 'lshin', 'hips'],
      size=(0.85, 1.2), material='card_indigo', pleats=2, pleat=0.09, hem=0.215, split=0.040, kick=0.0,
      hem_tilt=0.010, proportions=('standard', 'broad'), tags=('armour', 'legs'))
def hakama_shin_plain(ctx, P, rnd):
    """The plain leg below the knee: straight to the boot, a hem band but no flare."""
    return hakama_shin_pleated(ctx, dict(P, material='card_indigo'), rnd)


@part('hakama_apron', slot='armor', socket='obi', bone='hakama', bones=['lthigh', 'rthigh', 'hips'],
      rigid=False, size=(0.9, 1.15), layer=52,
      material='washi_natural', drop=0.24, width=0.135, tags=('reference', 'legs'),
      proportions=('slim', 'standard', 'broad'))
def hakama_apron(ctx, P, rnd):
    """The robe skirt below the obi: one sheet hanging over the leg tops, cut on the SAME diagonal as the lapel so the wrap reads through the belt; a back panel and the stiff koshiita board behind."""
    w, drop = P['width'], P['drop']
    zt = OBI_Z[0] + 0.035
    # front: long on the wearer's right, short on the left, one vertical fold; the split shows below it
    yT, yB = -OBI_HD + 0.012, -0.156
    xm = -w * 0.20
    zl, zr = zt - drop * 0.42, zt - drop
    zm = zr + (zl - zr) * (xm + w * 1.08) / (w * 2.12)
    pts = [(w, yT, zt), (xm, yT - 0.004, zt), (-w, yT, zt),
           (-w * 1.08, yB + 0.012, zr), (xm, yB - 0.016, zm), (w * 1.04, yB + 0.030, zl)]
    ob = ctx.add('hakama_apron_front', tidy(shell(pts, [(0, 1, 4, 5), (1, 2, 3, 4)])),
                 [ctx.mat(P.get('material', 'washi_bleached')), ctx.mat('washi_shade')],
                 thickness=0.010)
    # back: a plain trapezoid sheet over the back of the legs, with the koshiita board lapped over the obi
    yT, yB = OBI_HD - 0.012, 0.158
    bz = zt - drop * 0.62
    ctx.add('hakama_apron_back', tidy(shell([(-w * 0.85, yT, zt), (0, yT + 0.006, zt), (w * 0.85, yT, zt),
                                             (w * 1.05, yB, bz), (0, yB + 0.014, bz - 0.02),
                                             (-w * 1.05, yB, bz)], [(0, 1, 4, 5), (1, 2, 3, 4)])),
            [ctx.mat('washi_shade'), ctx.mat('seam_shadow')], thickness=0.009)
    return ob


@part('tabi_zori', slot='foot', socket=['ankle.L', 'ankle.R'], bone=None, size=(0.9, 1.15),
      material='washi_bleached', length=0.26, tags=('reference',), proportions=('slim', 'standard', 'broad'))
def tabi_zori(ctx, P, rnd):
    """Pointed tabi over a flat zori sole: a folded wedge with a split toe and a dark sole plate under it."""
    S, sg = ctx.socket, ctx.side
    x, L = S.x, P['length']
    heel, toe = 0.075, -L + 0.075
    pts = [(x - 0.050, heel, 0.004), (x + 0.050, heel, 0.004),                      # 0 1 heel sole
           (x + 0.044, toe + 0.03, 0.004), (x - 0.044, toe + 0.03, 0.004),          # 2 3 toe sole
           (x - 0.046, heel - 0.01, 0.092), (x + 0.046, heel - 0.01, 0.092),        # 4 5 ankle top
           (x + 0.020, toe + 0.055, 0.036), (x - 0.020, toe + 0.055, 0.036),        # 6 7 instep
           (x + 0.006, toe, 0.012), (x - 0.006, toe, 0.012)]                        # 8 9 the split toe point
    F = [(0, 1, 2, 3), (0, 3, 7, 4), (1, 5, 6, 2), (4, 7, 6, 5), (3, 2, 8, 9), (2, 6, 8), (3, 9, 7),
         (7, 9, 8, 6), (0, 4, 5, 1)]
    bm = shell(pts, F)
    bmesh.ops.translate(bm, vec=(0, 0, S.z), verts=bm.verts)
    ob = ctx.add(f'tabi_{"L" if sg > 0 else "R"}', bm,
                 [ctx.mat(P.get('material', 'washi_bleached')), ctx.mat('washi_shade')], thickness=0.005)
    ctx.add(f'zori_{"L" if sg > 0 else "R"}',
            panel([(x - 0.058, heel + 0.015, S.z - 0.004), (x + 0.058, heel + 0.015, S.z - 0.004),
                   (x + 0.050, toe + 0.01, S.z - 0.004), (x - 0.050, toe + 0.01, S.z - 0.004)]),
            [ctx.mat('card_indigo'), ctx.mat('seam_shadow')], thickness=0.010)
    return ob


@part('boot_plated', slot='foot', socket=['ankle.L', 'ankle.R'], bone=None, size=(0.9, 1.15),
      material='card_charcoal', length=0.27, proportions=('standard', 'broad'), tags=('armour',))
def boot_plated(ctx, P, rnd):
    """A heavy folded war boot: the same wedge in charcoal card with a shin plate above it."""
    S, sg = ctx.socket, ctx.side
    ob = tabi_zori(ctx, dict(P, material='card_charcoal'), rnd)
    ctx.add(f'suneate_{"L" if sg > 0 else "R"}',
            box(S.x, -0.055, S.z + 0.16, 0.085, 0.035, 0.17, rot=(-0.08, 0, 0)),
            [ctx.mat('card_charcoal'), ctx.mat('seam_shadow')], thickness=0.008)
    return ob


# =========================================================================== PARTS: armour and accessories
@part('sode_lamellar', slot='armor', socket=['shoulder.L', 'shoulder.R'], bone=None, size=(0.85, 1.2),
      material='card_charcoal', rows=4, cols=5, plate=0.048, proportions=('standard', 'broad'),
      tags=('armour',))
def sode_lamellar(ctx, P, rnd):
    """Sode: rows of lapped card scales over the shoulder, each row overhanging the one below."""
    S, sg = ctx.socket, ctx.side
    last = None
    for row in range(int(P['rows'])):
        z = S.z + 0.035 - row * (P['plate'] * 0.92)
        r = P['plate'] * (1.0 + row * 0.10)
        for k in range(int(P['cols'])):
            t = (k / (P['cols'] - 1) - 0.5) * 2
            last = ctx.add(f'sode_{row}_{k}_{"L" if sg > 0 else "R"}',
                           box(S.x + sg * (0.030 + row * 0.006), t * r * 1.9, z,
                               P['plate'] * 0.62, r * 0.92, P['plate'],
                               rot=(0, sg * (0.22 + row * 0.08), -t * 0.10)),
                           [ctx.mat('card_charcoal'), ctx.mat('seam_shadow')], thickness=0.008)
    return last


@part('do_plates', slot='armor', socket='chest', bone='upper', size=(0.85, 1.15), layer=62,
      material='card_charcoal', rows=4, proportions=('standard', 'broad'), tags=('armour',))
def do_plates(ctx, P, rnd):
    """Do: the cuirass as four lapped card bands across the chest, each with a dark slot under its lip."""
    cz = REST['upper'][2]
    last = None
    for row in range(int(P['rows'])):
        z = cz + 0.20 - row * 0.085
        w = 0.215 - row * 0.008
        pts = [(-w, -0.150 - row * 0.002, z), (w, -0.150 - row * 0.002, z),
               (w * 0.94, -0.168 - row * 0.002, z - 0.072), (-w * 0.94, -0.168 - row * 0.002, z - 0.072)]
        ctx.gap(f'do_gap_{row}', pts, push=(0, 0.010, 0), grow=0.004)
        last = ctx.add(f'do_{row}', panel(pts, bulge=-0.016),
                       [ctx.mat('card_charcoal'), ctx.mat('seam_shadow')], thickness=0.010)
    return last


@part('katana_sheathed', slot='accessory', socket=['hip_side.L', 'hip_side.R'], bone='torso', size=(0.9, 1.1),
      material='card_indigo', length=0.80, tilt=-14.0, swing=13.0, tsuka=0.22, proportions=('slim', 'standard', 'broad'))
def katana_sheathed(ctx, P, rnd):
    """The sword at the hip: a folded paper saya and tsuka in one line, mouth at the obi, tip low behind."""
    S, sg = ctx.socket, ctx.side
    mouth = Vector((S.x, S.y, S.z))
    tilt = (Matrix.Rotation(math.radians(P['tilt']), 3, 'X')
            @ Matrix.Rotation(math.radians(P['swing'] * sg), 3, 'Z'))
    last = None
    for nm, y0, y1, w, key in (('saya', 0.0, P['length'], 0.030, 'card_indigo'),
                               ('tsuka', -P['tsuka'], 0.0, 0.036, 'washi_shade')):
        bm = box(0, (y0 + y1) / 2, 0, w, y1 - y0, w * 0.82)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=tilt)
        bmesh.ops.translate(bm, vec=mouth, verts=bm.verts)
        last = ctx.add(nm, bm, [ctx.mat(key), ctx.mat('seam_shadow')], thickness=0.004)
    bm = box(0, 0, 0, 0.082, 0.010, 0.082)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=tilt)
    bmesh.ops.translate(bm, vec=mouth, verts=bm.verts)
    ctx.add('tsuba', bm, [ctx.mat('card_charcoal'), ctx.mat('seam_shadow')], thickness=0.004)
    return last


@part('tassels', slot='accessory', socket='obi', bone='torso', size=(0.9, 1.1),
      material='washi_natural', count=2, proportions=('slim', 'standard', 'broad'))
def tassels(ctx, P, rnd):
    """Two folded paper tassels on cords from the obi knot: the small bit of motion in a still frame."""
    hz = REST['torso'][2]
    last = None
    for k in range(int(P['count'])):
        x = 0.040 + k * 0.058
        ctx.add(f'tassel_cord_{k}', box(x, -OBI_HD - 0.046, hz + 0.02 - k * 0.02, 0.005, 0.006, 0.085),
                [ctx.mat('card_indigo'), ctx.mat('seam_shadow')], thickness=0.0)
        bm = bmesh.new()
        skin_rings(bm, [poly_ring(5, 0.020, hz - 0.030 - k * 0.02, cx=x, cy=-OBI_HD - 0.046),
                        poly_ring(5, 0.006, hz - 0.115 - k * 0.02, cx=x, cy=-OBI_HD - 0.046)], cap_first=True)
        last = ctx.add(f'tassel_{k}', bm, [ctx.mat('washi_natural', glow=True), ctx.mat('washi_shade')],
                       thickness=0.004)
    return last


# =========================================================================== reporting
# =========================================================================== generated parts (library/ai-parts.json)
# A generated part is DATA: tools/ai_part.py has already cut, fitted, reduced and painted it into <prepared>/
# (part.glb in the rig's rest space, with 'skin'/'hair' material slots, and ink/glow masks on its UVs). Here each
# manifest entry becomes an ordinary rigid part: a recipe names it, the builder binds it to its bone, and it is
# made of the same washi sheets as everything else, with the paint printed on top (pm.add_paint).
AI_PARTS_FILE = os.path.join(REPO, 'library', 'ai-parts.json')


def _glb_bmesh(path):
    """One mesh from a prepared part.glb as a bmesh, with its material slot names (skin, hair...) in face order."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    if len(meshes) != 1:
        raise ValueError(f'{path}: a prepared part holds exactly one mesh, found {len(meshes)}')
    o = meshes[0]
    names = [(m.name.rsplit('.', 1)[0] if m and '.' in m.name and m.name.rsplit('.', 1)[1].isdigit() else
              (m.name if m else '')) for m in o.data.materials]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.transform(bm, matrix=o.matrix_world, verts=bm.verts[:])
    imported_mats = [m for m in o.data.materials if m]
    for ob in new:
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in imported_mats:
        if m.users == 0:
            bpy.data.materials.remove(m)
    return bm, names


def _ai_part(pid, e):
    def _built(ctx, P, rnd):
        d = os.path.join(REPO, P['prepared'])
        bm, names = _glb_bmesh(os.path.join(d, 'part.glb'))
        sheets = P['sheets']
        mats = []
        lantern = P.get('lantern') or {}
        paint_on = P.get('paint_on') or ['skin']
        for nm in names:
            k = float(lantern.get(nm, 0.0))                    # the inner lantern through this sheet (mask: 1.0)
            m = ctx.mat(sheets.get(nm, sheets.get('skin', 'washi_natural')), glow=ctx.lit(k) if k > 0 else None)
            if nm in paint_on and (P.get('ink') or P.get('glow')):
                painted = bpy.data.materials.get(m.name + '_paint_' + pid)   # m.name carries the glow tag
                if painted is None:
                    painted = m.copy()
                    painted.name = m.name + '_paint_' + pid
                    ink = glow = None
                    if P.get('ink') and os.path.exists(os.path.join(d, 'ink.png')):
                        ink = (bpy.data.images.load(os.path.join(d, 'ink.png'), check_existing=True), P['ink'])
                    if P.get('glow') and os.path.exists(os.path.join(d, 'glow.png')):
                        g = P['glow']
                        glow = (bpy.data.images.load(os.path.join(d, 'glow.png'), check_existing=True),
                                g.get('rgb', ctx.glow[0]), float(g.get('strength', 6.0)))
                    pm.add_paint(painted, ink=ink, glow=glow)
                m = painted
            mats.append(m)
        # the geometry is already in rest space at its socket (tools/ai_part.py fitted it): no socket offset
        return ctx.add(pid, bm, mats, thickness=0.0, rim_mat=False)
    _built.__doc__ = e.get('label', pid)
    # rigid: one bone (a head, a hat, a foot). Otherwise skinned across `bones` by the builder exactly like the
    # folded sleeves and hakama (inverse distance to the bones' rest segments); 'l' bones mirror on a .R socket.
    rigid = bool(e.get('rigid', True))
    part(pid, slot=e['slot'], socket=e['socket'], bone=e.get('bone'), bones=None if rigid else e.get('bones'),
         rigid=rigid, size=(1.0, 1.0), layer=e.get('layer'),
         material=next(iter(e.get('sheets', {}).values()), 'washi_natural'), tags=('ai',),
         prepared=e['prepared'], sheets=e.get('sheets', {'skin': 'washi_natural'}), ink=e.get('ink'),
         glow=e.get('glow'), lantern=e.get('lantern'), paint_on=e.get('paint_on'), skin=e.get('skin'))(_built)


def load_ai_parts(path=AI_PARTS_FILE):
    """Register every prepared generated part in the manifest (entries whose <prepared>/part.glb exists)."""
    if not os.path.exists(path):
        return []
    import ai_manifest                         # one-block "body" characters expand into their sections
    done = []
    for pid, e in ai_manifest.load(path).items():
        if pid.startswith('_') or not isinstance(e, dict):
            continue
        if not os.path.exists(os.path.join(REPO, e['prepared'], 'part.glb')):
            continue                               # not prepared yet: python3 tools/ai_part.py ... first
        _ai_part(pid, e)
        done.append(pid)
    return done


load_ai_parts()


def describe(slots_only=False):
    out = ['SLOTS (what goes where, and what covers what)',
           f'{"slot":<16}{"layer":>6}  what it is']
    for s, (what, layer, _flex) in sorted(SLOTS.items(), key=lambda kv: kv[1][1]):
        out.append(f'{s:<16}{layer:>6}  {what}')
    if slots_only:
        return '\n'.join(out)
    out += ['', f'PARTS ({len(PARTS)} in the library)',
            f'{"part":<22}{"slot":<16}{"socket":<22}{"bind":<10}{"size":<12}{"material":<16}what it is']
    for name, p in sorted(PARTS.items(), key=lambda kv: (SLOTS[kv[1]['slot']][1], kv[0])):
        bind = 'rigid' if p['rigid'] else 'skin:%d' % max(len(p['bones']), 2)
        sock = ','.join(s.split('.')[0] for s in dict.fromkeys(s.split('.')[0] for s in p['socket']))
        if len(p['socket']) > 1:
            sock += ' L/R'
        out.append(f'{name:<22}{p["slot"]:<16}{sock:<22}{bind:<10}'
                   f'{"%.2f-%.2f" % p["size"]:<12}{p["material"]:<16}{p["doc"]}')
    out += ['', 'SOCKETS (attachment points in the rest pose: x, y, z metres → bone)']
    for s, d in SOCKETS.items():
        out.append(f'  {s:<14}({d["pos"][0]:+.3f}, {d["pos"][1]:+.3f}, {d["pos"][2]:.3f})  '
                   f'grows {d["grow"]:<6} bone {d["bone"]}')
    by_slot = {}
    for n, p in PARTS.items():
        by_slot.setdefault(p['slot'], []).append(n)
    thin = [s for s in ('hat', 'face', 'torso', 'sleeve_hanging', 'thigh', 'shin') if len(by_slot.get(s, [])) < 2]
    out += ['', 'variants per slot: ' + ', '.join(f'{s}={len(v)}' for s, v in sorted(by_slot.items()))]
    if thin:
        out.append('WARNING: important slots with fewer than 2 variants: ' + ', '.join(thin))
    return '\n'.join(out)


if __name__ == '__main__':
    print(describe(slots_only='--slots' in sys.argv))
