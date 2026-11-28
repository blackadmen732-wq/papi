"""SET KIT: reusable, procedural, seeded set pieces for Paper Cinema (Blender 4.5, Cycles).

A set is composed from pieces by a JSON file (library/sets/<name>.json, built by blender/sets/build_set.py).
Every piece is a function registered with @piece(name, **defaults): it receives a context (`ctx`), its params
(defaults merged with the JSON `params`) and a seeded random stream, and builds its geometry in LOCAL
coordinates (metres, Z up, the piece's front faces -Y). build_piece() places it with `pos` / `rot` / `scale`
under an empty named SET_<name>.

    import sys; sys.path.insert(0, 'blender/sets'); import kit
    ctx = kit.Ctx(bpy.context.scene, seed=1)
    kit.build_piece(ctx, {'kit': 'toro', 'name': 'lantern_L', 'pos': [-4, 2, 0], 'params': {'energy': 30}})

Look: realistic texture detail (stone grain, moss, grime, wood grain, plaster stains, tile lichen, AO, bump,
roughness variation; see the SET MATERIALS in blender/world/paper_materials.py) on geometry that stays in the
paper-craft family: flat facets (true-normal shading), folded edges, a faint washi-fibre bump everywhere.
Materials are procedural, with an optional Poly Haven photo layer (ph=role, library/polyhaven.json, on when a set
has "polyhaven": true). List every piece and its parameters with:  python3 blender/sets/kit.py --list
"""
import math
import os
import random
import sys
import zlib

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
from bl_compat import object_fcurves  # noqa: E402  (Blender 4.5 / 5.x shim)

try:
    import bmesh
    import bpy
    from mathutils import Euler, Matrix, Vector, noise
    HAVE_BPY = True
except ImportError:          # `python3 kit.py --list` outside Blender
    HAVE_BPY = False

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'world'))
if HAVE_BPY:
    import paper_materials as pm  # noqa: E402

KIT = {}


def piece(name, **defaults):
    """Register a set piece. Defaults double as the documented parameter list."""
    def deco(fn):
        KIT[name] = {'fn': fn, 'defaults': defaults, 'doc': (fn.__doc__ or '').strip()}
        return fn
    return deco


# =========================================================================== materials library
def _M():
    """Material recipes by key. JSON can override any keyword: "materials": {"plaster": {"color": [..]}}."""
    return {
        'stone': (pm.stone_material, dict(ph='stone')),
        'stone_dark': (pm.stone_material, dict(color=(0.13, 0.125, 0.115), color2=(0.24, 0.225, 0.20), moss=0.3, ph='stone')),
        'stone_mossy': (pm.stone_material, dict(color=(0.22, 0.21, 0.19), color2=(0.36, 0.34, 0.30), moss=0.85, grime=0.7, ph='stone_rough')),
        'stone_dressed': (pm.stone_material, dict(color=(0.36, 0.35, 0.32), color2=(0.48, 0.46, 0.42), moss=0.15, grime=0.4, flecks=0.4, ph='stone')),
        'stone_lantern': (pm.stone_material, dict(color=(0.30, 0.29, 0.26), color2=(0.42, 0.40, 0.36), moss=0.6, grime=0.8, scale=2.5, ph='stone_rough')),
        'backfill': (pm.stone_material, dict(color=(0.035, 0.033, 0.03), color2=(0.07, 0.065, 0.06), moss=0.0, grime=0.9, paper=0.0)),
        'plaster': (pm.plaster_material, dict(ph='plaster')),
        'plaster_old': (pm.plaster_material, dict(color=(0.70, 0.66, 0.58), grime=0.9, cracks=0.7, ph='plaster')),
        'plaster_earth': (pm.plaster_material, dict(color=(0.42, 0.31, 0.20), grime=0.4, cracks=0.2, ph='plaster')),
        'wood': (pm.wood_material, dict(ph='wood')),
        'wood_dark': (pm.wood_material, dict(color=(0.045, 0.032, 0.025), color2=(0.02, 0.016, 0.013), rough=0.55, wear=0.35, ph='wood')),
        'wood_aged': (pm.wood_material, dict(color=(0.20, 0.18, 0.155), color2=(0.10, 0.09, 0.08), rough=0.85, wear=0.2, ph='wood')),
        'wood_light': (pm.wood_material, dict(color=(0.55, 0.40, 0.25), color2=(0.38, 0.25, 0.14), rough=0.55, wear=0.1, ph='wood')),
        'wood_floor': (pm.wood_material, dict(color=(0.36, 0.22, 0.12), color2=(0.20, 0.11, 0.055), polish=0.55, rough=0.42, wear=0.25, ph='wood_floor')),
        'wood_floor_y': (pm.wood_material, dict(color=(0.36, 0.22, 0.12), color2=(0.20, 0.11, 0.055), polish=0.55, rough=0.42, wear=0.25, axis='Y', ph='wood_floor')),
        'wood_post': (pm.wood_material, dict(color=(0.16, 0.095, 0.055), color2=(0.08, 0.045, 0.025), axis='Z', rough=0.55, wear=0.3, ph='wood')),
        'wood_dark_z': (pm.wood_material, dict(color=(0.045, 0.032, 0.025), color2=(0.02, 0.016, 0.013), axis='Z', rough=0.55, wear=0.35, ph='wood')),
        'tile': (pm.tile_material, dict(ph='roof_tiles')),
        'lacquer_red': (pm.lacquer_material, dict()),
        'lacquer_black': (pm.lacquer_material, dict(color=(0.018, 0.016, 0.015), under=(0.08, 0.05, 0.03), wear=0.2)),
        'shoji': (pm.shoji_material, dict()),
        'lantern_paper': (pm.shoji_material, dict(color=(0.95, 0.85, 0.65), translucency=0.75, glow=((1.0, 0.55, 0.2), 1.5), stains=0.2)),
        'tatami': (pm.tatami_material, dict(ph='tatami')),
        'tatami_border': (pm.paper_material, dict(color=(0.02, 0.025, 0.04), translucency=0.0, fibre_scale=80, facet_var=0.02)),
        'gravel': (pm.gravel_material, dict(ph='gravel')),
        'gravel_wet': (pm.gravel_material, dict(color=(0.22, 0.215, 0.20), wet=0.6, ph='gravel')),
        'sand': (pm.gravel_material, dict(color=(0.50, 0.42, 0.31), scale=70.0, ph='sand')),
        'earth': (pm.earth_material, dict(ph='earth')),
        'forest_floor': (pm.earth_material, dict(color=(0.12, 0.09, 0.06), moss=0.6, leaves=0.5, leaf_color=(0.30, 0.25, 0.10), ph='forest_floor')),
        'bamboo': (pm.bamboo_material, dict(ph='bamboo')),
        'bamboo_node': (pm.bamboo_material, dict(color=(0.22, 0.24, 0.08), age=0.7, ph='bamboo')),
        'bamboo_leaf': (pm.foliage_material, dict(color=(0.09, 0.14, 0.035), trans=(0.30, 0.42, 0.06), translucency=0.4)),
        'pine_needle': (pm.foliage_material, dict(color=(0.035, 0.06, 0.03), trans=(0.12, 0.2, 0.05), translucency=0.25)),
        'blossom': (pm.foliage_material, dict(color=(0.85, 0.55, 0.60), trans=(1.0, 0.62, 0.70), translucency=0.45, var=0.2)),
        'maple_red': (pm.foliage_material, dict(color=(0.45, 0.06, 0.02), trans=(0.9, 0.25, 0.05), translucency=0.4)),
        'bark': (pm.bark_material, dict(ph='bark')),
        'bark_cherry': (pm.bark_material, dict(color=(0.09, 0.055, 0.05), moss=0.35, ph='bark_cherry')),
        'iron': (pm.iron_material, dict()),
        'gold': (pm.gold_material, dict()),
        'window_glow': (pm.glow_window_material, dict()),
        'window_dark': (pm.paper_material, dict(color=(0.012, 0.011, 0.01), translucency=0.0, fibre_scale=20, facet_var=0.02)),
        'paper': (pm.paper_material, dict(color=(0.80, 0.76, 0.67), translucency=0.3, fibre_scale=60)),
        'cloth_dark': (pm.paper_material, dict(color=(0.03, 0.03, 0.035), translucency=0.0, fibre_scale=60)),
        'cloth_red': (pm.paper_material, dict(color=(0.35, 0.03, 0.02), translucency=0.2, fibre_scale=60)),
        'rain': (pm.rain_material, dict()),
        'ember': (pm.emission_material, dict(color=(1.0, 0.35, 0.08), strength=30.0)),
        'petal': (pm.foliage_material, dict(color=(0.92, 0.62, 0.68), trans=(1.0, 0.7, 0.75), translucency=0.5, var=0.15)),
        'dust': (pm.emission_material, dict(color=(1.0, 0.85, 0.6), strength=0.6)),
    }


# =========================================================================== context
class Ctx:
    """Shared state while a set is built: scene, target collection, seed, material cache, lights, clear zones."""

    def __init__(self, scene, collection=None, seed=1, materials=None):
        self.scene = scene
        if collection is None:
            collection = bpy.data.collections.new('SET')
            scene.collection.children.link(collection)
        self.coll = collection
        self.seed = seed
        self.overrides = materials or {}
        self._mats = {}
        self.root = None
        self.clear = []          # [(x, y, r)] world-space zones kept free of scattered props (fighter marks)
        self.fight = []          # [(x, y, r)] the fighter marks alone: ground pieces level the terrain there
        self.lights = []
        self.info = {}

    def rng(self, *keys):
        return random.Random(':'.join(str(k) for k in (self.seed,) + keys))

    def mat(self, key):
        if key in self._mats:
            return self._mats[key]
        recipes = _M()
        base = key.split('#')[0]                 # 'stone#2' = a second copy of the stone recipe (own overrides)
        if base not in recipes:
            raise KeyError(f'unknown material {key!r}; known: {", ".join(sorted(recipes))}')
        fn, kw = recipes[base]
        kw = dict(kw)
        for k, v in self.overrides.get(key, {}).items():
            kw[k] = tuple(v) if isinstance(v, list) else v
        if 'color' in kw and fn is pm.emission_material:
            m = fn('SET_' + key, kw['color'], kw.get('strength', 1.0))
        else:
            m = fn('SET_' + key, **kw)
        self._mats[key] = m
        return m

    def link(self, ob, parent=True):
        self.coll.objects.link(ob)
        if parent and self.root is not None:
            ob.parent = self.root
        return ob

    def light(self, kind, loc, energy, color=(1, 1, 1), size=0.1, look=None, spot=None, name='light', blend=0.3):
        L = bpy.data.lights.new(name, kind)
        L.energy = energy
        L.color = tuple(color)[:3]
        if kind in ('POINT', 'SPOT'):
            L.shadow_soft_size = size
        elif kind == 'AREA':
            L.shape = 'RECTANGLE' if isinstance(size, (list, tuple)) else 'SQUARE'
            if isinstance(size, (list, tuple)):
                L.size, L.size_y = size
            else:
                L.size = size
        elif kind == 'SUN':
            L.angle = math.radians(size)
        if kind == 'SPOT':
            L.spot_size = math.radians(spot or 40)
            L.spot_blend = blend
        ob = bpy.data.objects.new(name, L)
        ob.location = Vector(loc)
        if look is not None:
            ob.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        self.link(ob)
        self.lights.append(ob)
        return ob

    def world_xy(self, local):
        """Local point -> world (uses the current piece root's matrix)."""
        if self.root is None:
            return Vector(local)
        return self.root.matrix_world @ Vector(local)

    def is_clear(self, local_xy, pad=0.0):
        w = self.world_xy((local_xy[0], local_xy[1], 0))
        return all(math.hypot(w.x - x, w.y - y) > r + pad for x, y, r in self.clear)


# =========================================================================== mesh builder
def _rot(r):
    if r is None:
        return Matrix.Identity(3)
    if isinstance(r, Matrix):
        return r.to_3x3()
    return Euler(tuple(math.radians(a) for a in r), 'XYZ').to_matrix()


def M4(loc=(0, 0, 0), rot=None, scale=(1, 1, 1)):
    return Matrix.LocRotScale(Vector(loc), _rot(rot), Vector(scale))


class MB:
    """Accumulates many parts into one mesh, with a material slot per key and a per-part random
    (`piece_rand` face attribute) so materials can vary stone by stone, plank by plank."""

    def __init__(self, ctx, name, rnd=None):
        self.ctx, self.name = ctx, name
        self.rnd = rnd or random.Random(zlib.crc32(name.encode()))
        self.bm = bmesh.new()
        self.pl = self.bm.faces.layers.float.new(pm.PIECE_ATTR)
        self.keys = []

    def mi(self, key):
        if key not in self.keys:
            self.keys.append(key)
        return self.keys.index(key)

    def tag(self, faces, key, pr=None):
        mi = self.mi(key)
        pr = self.rnd.random() if pr is None else pr
        for f in faces:
            f.material_index = mi
            f[self.pl] = pr
        return faces

    @staticmethod
    def faces_of(verts):
        return {f for v in verts for f in v.link_faces}

    def box(self, key, size, loc=(0, 0, 0), rot=None, pr=None, bevel=0.0, matrix=None):
        """Axis box of `size` centred on `loc`, optionally bevelled (folded edges catch the light)."""
        m = (matrix or Matrix.Identity(4)) @ M4(loc, rot, size)
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        vs = res['verts']
        pr = self.rnd.random() if pr is None else pr
        faces = self.tag(self.faces_of(vs), key, pr)
        if bevel > 0:
            edges = list({e for v in vs for e in v.link_edges})
            out = bmesh.ops.bevel(self.bm, geom=list(vs) + edges, offset=bevel, segments=1, affect='EDGES', clamp_overlap=True)
            self.tag(set(out['faces']), key, pr)
        return faces

    def cyl(self, key, r1, r2, depth, segs=8, loc=(0, 0, 0), rot=None, pr=None, caps=True, matrix=None):
        m = (matrix or Matrix.Identity(4)) @ M4(loc, rot)
        res = bmesh.ops.create_cone(self.bm, cap_ends=caps, segments=segs, radius1=r1, radius2=r2, depth=depth, matrix=m)
        return self.tag(self.faces_of(res['verts']), key, pr)

    def poly(self, key, pts, pr=None):
        vs = [self.bm.verts.new(Vector(p)) for p in pts]
        f = self.bm.faces.new(vs)
        return self.tag({f}, key, pr)

    def stone(self, key, size, matrix, rnd, detail=1, square=0.42, bulge=0.12, chip=0.07, pr=None, flat_back=True):
        """One irregular stone: a squarified icosphere (boxy but rounded, chipped facets) of `size` (w, d, h),
        displaced by 3D noise. `square` < 1 squares it off (0.3 = dressed block, 0.6 = river stone)."""
        res = bmesh.ops.create_icosphere(self.bm, subdivisions=detail, radius=1.0)
        seed = Vector((rnd.uniform(-99, 99), rnd.uniform(-99, 99), rnd.uniform(-99, 99)))
        f1 = rnd.uniform(1.2, 2.2)
        for v in res['verts']:
            p = v.co
            q = Vector([math.copysign(abs(c) ** square, c) for c in p])
            n = noise.noise(p * f1 + seed) * chip + noise.noise(p * f1 * 2.7 + seed) * chip * 0.5
            q = q * (1.0 + n)
            if q.y < 0:                      # the visible face (-Y) bulges a little
                q.y -= bulge * (1 - min(1, q.x * q.x + q.z * q.z))
            elif flat_back:
                q.y = min(q.y, 0.85)
            v.co = matrix @ Vector((q.x * size[0] / 2, q.y * size[1] / 2, q.z * size[2] / 2))
        return self.tag(self.faces_of(res['verts']), key, pr)

    def grid(self, key, fn, nu, nv, pr_fn=None, closed_u=False):
        """Surface from fn(u, v) -> (x, y, z) on a (nu+1) x (nv+1) grid; pr_fn(i, j) gives per-face piece random."""
        rows = []
        for j in range(nv + 1):
            rows.append([self.bm.verts.new(Vector(fn(i / nu, j / nv))) for i in range(nu + (0 if closed_u else 1))])
        mi = self.mi(key)
        cols = nu if closed_u else nu
        for j in range(nv):
            for i in range(cols):
                i2 = (i + 1) % nu if closed_u else i + 1
                f = self.bm.faces.new((rows[j][i], rows[j][i2], rows[j + 1][i2], rows[j + 1][i]))
                f.material_index = mi
                f[self.pl] = pr_fn(i, j) if pr_fn else 0.5
        return rows

    def tube(self, key, pts, radii, segs=7, pr=None, cap=True, twist=0.0):
        """Tapered tube through points (trunks, branches, culms); flat facets like a folded paper tube."""
        rings = []
        up = Vector((0, 0, 1))
        for i, p in enumerate(pts):
            p = Vector(p)
            t = (Vector(pts[min(i + 1, len(pts) - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
            ref = up if abs(t.dot(up)) < 0.95 else Vector((1, 0, 0))
            a = t.cross(ref).normalized()
            b = t.cross(a).normalized()
            ring = []
            for k in range(segs):
                ang = 2 * math.pi * k / segs + twist * i
                ring.append(self.bm.verts.new(p + (a * math.cos(ang) + b * math.sin(ang)) * radii[i]))
            rings.append(ring)
        faces = []
        for i in range(len(rings) - 1):
            for k in range(segs):
                faces.append(self.bm.faces.new((rings[i][k], rings[i][(k + 1) % segs], rings[i + 1][(k + 1) % segs], rings[i + 1][k])))
        if cap:
            faces.append(self.bm.faces.new(rings[-1]))
        return self.tag(set(faces), key, pr)

    def finish(self, smooth=False, parent=True, shadow=True):
        me = bpy.data.meshes.new(self.name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        ob = bpy.data.objects.new(self.name, me)
        for k in self.keys:
            me.materials.append(self.ctx.mat(k))
        for p in me.polygons:
            p.use_smooth = smooth
        pm.add_facet_attribute(ob, zlib.crc32(self.name.encode()) & 0xffff)
        ob.visible_shadow = shadow
        return self.ctx.link(ob, parent)


# =========================================================================== tiled roofs (kawara)
def tile_profile(x, amp):
    """Cross profile of hongawara roofing, x in tile periods: a round cover tile (marugawara) then a concave pan."""
    f = x % 1.0
    if f < 0.32:
        return amp * math.sin(math.pi * f / 0.32) ** 0.7
    return -amp * 0.28 * math.sin(math.pi * (f - 0.32) / 0.68)


def tile_patch(mb, E0, E1, R0, R1, *, tile_w=0.30, tile_l=0.34, amp=0.07, v_max=1.0, sori=1.35, upturn=0.0,
               key='tile', end_caps=True, res=6, ridge_u=None):
    """A bilinear roof slope from the eave edge E0-E1 to the ridge edge R0-R1 (R0 == R1 for a hip triangle),
    with tile relief: round cover tiles in columns down the slope, a step at every tile course, a concave
    (sori) section and optional upturned corners. Returns a function P(u, v) giving surface points."""
    E0, E1, R0, R1 = Vector(E0), Vector(E1), Vector(R0), Vector(R1)
    elen = (E1 - E0).length
    slen = ((R0 + R1) / 2 - (E0 + E1) / 2).length
    U = (E1 - E0).normalized()

    def base(u, v):
        e = E0.lerp(E1, u)
        r = R0.lerp(R1, u)
        p = e.lerp(r, v)
        p.z = e.z + (r.z - e.z) * (v ** sori)
        if upturn:
            p.z += upturn * (abs(2 * u - 1) ** 3) * (1 - v) ** 2
        return p

    nu = max(4, int(elen / tile_w * res))
    nv = max(3, int(slen * v_max / tile_l * 3))
    n_up = Vector((0, 0, 1))

    def P(u, v):
        vv = v * v_max
        p = base(u, vv)
        um = (p - E0).dot(U) / tile_w
        vm = vv * slen / tile_l
        step = amp * 0.35 * (1 - (vm % 1.0))
        p = p + n_up * (tile_profile(um, amp) + step)
        return p

    hseed = zlib.crc32(mb.name.encode()) % 997

    def prf(i, j):                    # one stable random per tile (cheap integer hash, deterministic)
        k = (int(i / res) * 7919 + int(j / 3) * 104729 + hseed) * 2654435761
        return (k % 4294967296) / 4294967296.0
    mb.grid(key, P, nu, nv, prf)
    if end_caps:                      # round end tiles (nokigawara) along the eave, facing out
        out = (E0 + E1) / 2 - (R0 + R1) / 2
        out.z = 0
        out = out.normalized()
        ncol = int(elen / tile_w)
        for c in range(ncol):
            u = (c + 0.16) * tile_w / elen
            if u > 1:
                break
            p = base(u, 0.0) + n_up * (amp * 0.55)
            rot = out.to_track_quat('Z', 'Y').to_matrix()
            mb.cyl(key, amp * 0.85, amp * 0.85, 0.04, 8, matrix=Matrix.Translation(p) @ rot.to_4x4())
    return base


def beam_between(mb, key, a, b, w, h, pr=None):
    """Box beam from point a to b with cross-section w x h (ridges, hips, rafters, branches)."""
    a, b = Vector(a), Vector(b)
    d = b - a
    L = d.length
    if L < 1e-6:
        return set()
    q = d.normalized().to_track_quat('X', 'Z')
    return mb.box(key, (L, w, h), loc=(a + b) / 2, rot=q.to_matrix(), pr=pr)


def hip_roof(mb, W, D, *, pitch=30.0, overhang=1.2, upturn=0.35, sori=1.35, v_max=1.0, tile_w=0.30, tile_l=0.34,
             amp=0.07, ridge=True, soffit='plaster', fascia=0.22, z0=0.0, shachi=None, key='tile', hips=True):
    """Hip roof (yosemune) over a W x D footprint (W >= D) whose eave sits at z0; `v_max` < 1 truncates it into a
    pent roof (the skirt between castle storeys). Upturned corners, concave slopes, tiled, white plaster eaves."""
    o = overhang
    Wo, Do = W / 2 + o, D / 2 + o
    r = max(0.0, (W - D) / 2)
    rise = Do * math.tan(math.radians(pitch))
    z = z0
    corners = [Vector((-Wo, -Do, z)), Vector((Wo, -Do, z)), Vector((Wo, Do, z)), Vector((-Wo, Do, z))]
    rends = [Vector((-r, 0, z + rise)), Vector((r, 0, z + rise))]
    kw = dict(tile_w=tile_w, tile_l=tile_l, amp=amp, v_max=v_max, sori=sori, upturn=upturn, key=key)
    tile_patch(mb, corners[0], corners[1], rends[0], rends[1], **kw)                 # front
    tile_patch(mb, corners[2], corners[3], rends[1], rends[0], **kw)                 # back
    tile_patch(mb, corners[1], corners[2], rends[1], rends[1], **kw)                 # right (triangle)
    tile_patch(mb, corners[3], corners[0], rends[0], rends[0], **kw)                 # left
    up = Vector((0, 0, 1))

    def hip_pt(c, re, v):
        p = c.lerp(re, v)
        p.z = c.z + (re.z - c.z) * v ** sori + upturn * (1 - v) ** 2
        return p
    if hips:
        for c, re in ((corners[0], rends[0]), (corners[1], rends[1]), (corners[2], rends[1]), (corners[3], rends[0])):
            n = 6
            pts = [hip_pt(c, re, v_max * i / n) + up * (amp * 1.3) for i in range(n + 1)]
            for i in range(n):
                beam_between(mb, key, pts[i], pts[i + 1], 0.32, 0.26)
            mb.box(key, (0.34, 0.34, 0.42), loc=pts[0] + up * 0.12)          # end ornament at the corner
    if ridge and v_max >= 0.999:
        L = 2 * r + 0.5
        top = z + rise + amp * 1.3
        mb.box(key, (L, 0.42, 0.55), loc=(0, 0, top + 0.12), bevel=0.03)
        mb.box(key, (L - 0.1, 0.3, 0.16), loc=(0, 0, top + 0.47))
        for sx in (-1, 1):                                                     # onigawara end blocks
            mb.box(key, (0.3, 0.6, 0.8), loc=(sx * L / 2, 0, top + 0.3), bevel=0.04)
            if shachi:
                _shachihoko(mb, shachi, Vector((sx * (L / 2 - 0.15), 0, top + 0.65)), sx)
    # eave: fascia band + soffit back to the wall line (white plaster under the eaves, castle style)
    if soffit:
        n = 10
        ring_out, ring_in = [], []
        for side in range(4):
            a, b = corners[side], corners[(side + 1) % 4]
            for i in range(n):
                u = i / n
                p = a.lerp(b, u)
                p.z = z + upturn * abs(2 * u - 1) ** 3 - fascia
                ring_out.append(p)
                q = Vector((p.x * (W / 2) / Wo, p.y * (D / 2) / Do, z - fascia - o * 0.12))
                ring_in.append(q)
        N = len(ring_out)
        for i in range(N):
            j = (i + 1) % N
            mb.poly(soffit, [ring_out[i], ring_out[j], ring_in[j], ring_in[i]], pr=0.5)
            top_i = ring_out[i] + up * fascia
            top_j = ring_out[j] + up * fascia
            mb.poly(soffit, [ring_out[j], ring_out[i], top_i, top_j], pr=0.4)
    return rise


def _shachihoko(mb, key, p, sx):
    """Golden tiger-fish ridge ornament (a few folded facets: tail up, head down)."""
    mb.box(key, (0.22, 0.18, 0.5), loc=p + Vector((0, 0, 0.1)), rot=(0, sx * 12, 0), bevel=0.03)
    mb.box(key, (0.16, 0.06, 0.38), loc=p + Vector((-sx * 0.12, 0, 0.45)), rot=(0, -sx * 35, 0))
    mb.box(key, (0.2, 0.2, 0.18), loc=p + Vector((sx * 0.08, 0, -0.12)), rot=(0, sx * 30, 0))


def gable_roof(mb, L, Wd, *, pitch=32.0, overhang=0.35, z0=0.0, tile_w=0.26, tile_l=0.3, amp=0.05, key='tile',
               fascia='wood_dark', ridge=True, axis='X', offset=(0, 0, 0), end_caps=True):
    """Two-slope roof along `axis` (wall caps, gates, gables): length L, span Wd, eave at z0, centred on offset."""
    o = overhang
    hl, hw = L / 2 + o * 0.6, Wd / 2 + o
    rise = hw * math.tan(math.radians(pitch))
    off = Vector(offset)
    sw = (lambda x, y, z: Vector((x, y, z)) + off) if axis == 'X' else (lambda x, y, z: Vector((y, -x, z)) + off)
    kw = dict(tile_w=tile_w, tile_l=tile_l, amp=amp, sori=1.15, key=key, end_caps=end_caps)
    tile_patch(mb, sw(-hl, -hw, z0), sw(hl, -hw, z0), sw(-hl, 0, z0 + rise), sw(hl, 0, z0 + rise), **kw)
    tile_patch(mb, sw(hl, hw, z0), sw(-hl, hw, z0), sw(hl, 0, z0 + rise), sw(-hl, 0, z0 + rise), **kw)
    if ridge:
        a, b = sw(-hl, 0, z0 + rise + amp + 0.08), sw(hl, 0, z0 + rise + amp + 0.08)
        beam_between(mb, key, a, b, 0.3, 0.26)
        for e in (a, b):
            mb.box(key, (0.22, 0.4, 0.4) if axis == 'X' else (0.4, 0.22, 0.4), loc=e + Vector((0, 0, 0.12)))
    if fascia:
        for sy in (-1, 1):
            a, b = sw(-hl, sy * hw, z0 - 0.12), sw(hl, sy * hw, z0 - 0.12)
            beam_between(mb, fascia, a, b, 0.06, 0.16)
        for sx in (-1, 1):                 # barge boards on the gable ends
            for sy in (-1, 1):
                beam_between(mb, fascia, sw(sx * hl, sy * hw, z0 - 0.05), sw(sx * hl, 0, z0 + rise), 0.05, 0.2)
    return rise


# =========================================================================== stone walls (ishigaki)
def _profile(H, batter, curve):
    """Setback s(z) of a battered wall: shallow at the base, near vertical at the top (ogi-no-kobai)."""
    def s(z):
        t = min(1.0, max(0.0, z / H))
        return batter * (1 - (1 - t) ** curve)

    def ds(z):
        t = min(1.0, max(0.0, z / H))
        return batter * curve * (1 - t) ** (curve - 1) / H
    return s, ds


def _rows(rnd, H, stone):
    rows, z = [], 0.0
    while z < H - 0.05:
        k = 1.25 - 0.45 * z / H
        h = min(H - z, stone * k * rnd.uniform(0.75, 1.25))
        if H - z - h < stone * 0.35:
            h = H - z
        rows.append((z, h))
        z += h
    return rows


def stone_face(mb, rnd, L, H, rows, s, ds, *, stone=0.6, key='stone', detail=1, matrix=None, x_clip=None,
               corner_left=False, corner_right=False, fillers=0.5, style='nozura'):
    """Stones of one battered face (local: face toward -Y, x along the wall). x_clip(z) -> (x0, x1) limits each
    course (the inset corners of a battered base). corner_*: alternate long corner blocks (sangi-zumi)."""
    matrix = matrix or Matrix.Identity(4)
    gap = 0.035 * stone
    sq = {'nozura': 0.45, 'uchikomi': 0.33, 'kirikomi': 0.22}[style]
    for ri, (z0, h) in enumerate(rows):
        zc = z0 + h / 2
        x0, x1 = x_clip(zc) if x_clip else (-L / 2, L / 2)
        tilt = math.atan(ds(zc))
        y_face = s(zc)
        Db = h * 1.15                       # corner block depth seen from the other face
        xa, xb = x0, x1
        blocks = []
        if corner_right:
            if ri % 2 == 0:
                Lb = h * rnd.uniform(2.0, 2.6)
                blocks.append((x1 - Lb / 2, Lb, h * 1.15))
                xb = x1 - Lb - gap
            else:
                xb = x1 - Db - gap
        if corner_left:
            if ri % 2 == 1:
                Lb = h * rnd.uniform(2.0, 2.6)
                blocks.append((x0 + Lb / 2, Lb, h * 1.15))
                xa = x0 + Lb + gap
            else:
                xa = x0 + Db + gap
        x = xa
        joints = []
        while x < xb - 0.15 * stone:
            w = h * rnd.uniform(0.9, 2.1) * (1.15 if style == 'kirikomi' else 1.0)
            if xb - (x + w) < h * 0.55:
                w = xb - x
            xc = x + w / 2
            d = h * rnd.uniform(1.0, 1.5)
            pro = h * rnd.uniform(0.0, 0.1) if style == 'nozura' else h * rnd.uniform(0.0, 0.03)
            zj = zc + rnd.uniform(-0.05, 0.05) * h
            m = matrix @ M4((xc, y_face - pro + d / 2, zj), Euler((tilt + rnd.uniform(-0.04, 0.04), rnd.uniform(-0.05, 0.05), rnd.uniform(-0.04, 0.04))).to_matrix())
            mb.stone(key, (w - gap, d, h - gap), m, rnd, detail=detail, square=sq + rnd.uniform(-0.05, 0.08),
                     bulge=0.14 if style == 'nozura' else 0.05, chip=0.08 if style == 'nozura' else 0.04)
            joints.append(x + w)
            x += w + gap
        for xc, Lb, d in blocks:
            m = matrix @ M4((xc, y_face + d / 2 - 0.01, zc), Euler((tilt, 0, 0)).to_matrix())
            mb.stone(key, (Lb - gap, d, h - gap), m, rnd, detail=detail, square=0.25, bulge=0.04, chip=0.035)
        for xj in joints[:-1]:                # small wedge stones (aiishi) in the joints
            if rnd.random() < fillers:
                hs = h * rnd.uniform(0.18, 0.32)
                zz = z0 + rnd.uniform(0.15, 0.85) * h
                m = matrix @ M4((xj, s(zz) + hs * 0.3, zz), Euler((math.atan(ds(zz)), 0, rnd.uniform(0, 6))).to_matrix())
                mb.stone(key, (hs * 1.4, hs, hs), m, rnd, detail=1, square=0.5, bulge=0.05)


def backfill(mb, L, H, s, matrix, x_clip=None, key='backfill', inset=0.08, n=14):
    """The dark packed rubble seen in the gaps between stones."""
    def P(u, v):
        z = v * H
        x0, x1 = x_clip(z) if x_clip else (-L / 2, L / 2)
        return matrix @ Vector((x0 + (x1 - x0) * u, s(z) + inset, z))
    mb.grid(key, P, 8, n)


@piece('ishigaki', length=20.0, height=4.0, batter=1.6, curve=2.2, thickness=4.0, stone=0.6, detail=1, style='nozura',
       key='stone', top='earth', fillers=0.5, ends='cut')
def ishigaki(ctx, P, rnd):
    """Castle stone wall (ishigaki): a battered, concave-curved face of individual irregular stones (nozura /
    uchikomi / kirikomi style), small wedge stones in the joints, dark rubble in the gaps, moss and grime from the
    stone material. Face toward -Y, x along the wall, base on z = 0, top plateau `thickness` deep."""
    L, H = P['length'], P['height']
    s, ds = _profile(H, P['batter'], P['curve'])
    rows = _rows(rnd, H, P['stone'])
    mb = MB(ctx, ctx.info['name'] + '_stones', rnd)
    stone_face(mb, rnd, L, H, rows, s, ds, stone=P['stone'], key=P['key'], detail=P['detail'], style=P['style'], fillers=P['fillers'])
    mb.finish()
    bf = MB(ctx, ctx.info['name'] + '_core', rnd)
    backfill(bf, L, H, s, Matrix.Identity(4))
    T = s(H)
    bf.box(P['top'], (L, P['thickness'], 0.2), loc=(0, T + P['thickness'] / 2, H - 0.08))
    bf.box('backfill', (L, P['thickness'], H), loc=(0, T + P['thickness'] / 2 + 0.1, H / 2 - 0.1))
    bf.finish()


def ishigaki_block(ctx, rnd, w, d, H, *, batter=1.6, curve=2.2, stone=0.7, detail=1, style='uchikomi', key='stone',
                   top='earth', name='base', faces=(0, 1, 2, 3), at=(0, 0, 0), mb=None, bf=None):
    """Closed four-sided battered stone base (under a keep or a gate tower), corners in sangi-zumi.
    `at` moves it inside the piece; pass `mb`/`bf` builders to merge several blocks into one mesh."""
    s, ds = _profile(H, batter, curve)
    rows = _rows(rnd, H, stone)
    own = mb is None
    mb = mb or MB(ctx, name + '_stones', rnd)
    bf = bf or MB(ctx, name + '_core', rnd)
    at = Vector(at)
    for k in range(4):
        side = w if k % 2 == 0 else d
        other = d if k % 2 == 0 else w
        ang = [0, 90, 180, 270][k]
        m = Matrix.Translation(at) @ M4(rot=(0, 0, ang)) @ Matrix.Translation((0, -other / 2, 0))
        clip = (lambda L: (lambda z: (-L / 2 + s(z), L / 2 - s(z))))(side)
        if k in faces:
            stone_face(mb, rnd, side, H, rows, s, ds, stone=stone, key=key, detail=detail, matrix=m, x_clip=clip,
                       corner_left=True, corner_right=True, style=style)
        backfill(bf, side, H, s, m, x_clip=clip)
    T = s(H)
    bf.box(top, (w - 2 * T, d - 2 * T, 0.2), loc=at + Vector((0, 0, H - 0.09)))
    bf.box('backfill', (w - 2 * T - 0.2, d - 2 * T - 0.2, H), loc=at + Vector((0, 0, H / 2 - 0.1)))
    if own:
        mb.finish()
        bf.finish()
    return T


@piece('ishigaki_base', width=16.0, depth=13.0, height=6.0, batter=1.8, curve=2.2, stone=0.7, detail=1,
       style='uchikomi', key='stone', top='earth')
def ishigaki_base(ctx, P, rnd):
    """Four-sided battered stone platform (tenshu-dai) with sangi-zumi corners. Top at z = height."""
    ishigaki_block(ctx, rnd, P['width'], P['depth'], P['height'], batter=P['batter'], curve=P['curve'], stone=P['stone'],
                   detail=P['detail'], style=P['style'], key=P['key'], top=P['top'], name=ctx.info['name'])


# =========================================================================== list (outside Blender too)
def describe():
    lines = []
    for name, k in KIT.items():
        lines.append(f"{name}: {k['doc'].splitlines()[0] if k['doc'] else ''}")
        lines.append('    ' + ', '.join(f'{p}={v!r}' for p, v in k['defaults'].items()))
    return '\n'.join(lines)


def build_piece(ctx, spec):
    """Place one piece from a JSON spec: {kit, name, pos, rot (deg about Z, or [x,y,z]), scale, seed, params}."""
    kind = spec['kit']
    if kind not in KIT:
        raise KeyError(f'unknown kit piece {kind!r}; known: {", ".join(sorted(KIT))}')
    k = KIT[kind]
    P = dict(k['defaults'])
    unknown = set(spec.get('params', {})) - set(P)
    if unknown:
        print(f'  ! {spec.get("name", kind)}: unknown params {sorted(unknown)} for {kind} (known: {sorted(P)})')
    P.update(spec.get('params', {}))
    name = spec.get('name', kind)
    root = bpy.data.objects.new('SET_' + name, None)
    root.empty_display_size = 0.5
    root.location = Vector(spec.get('pos', (0, 0, 0)))
    r = spec.get('rot', 0)
    root.rotation_euler = tuple(math.radians(a) for a in r) if isinstance(r, (list, tuple)) else (0, 0, math.radians(r))
    sc = spec.get('scale', 1.0)
    root.scale = tuple(sc) if isinstance(sc, (list, tuple)) else (sc, sc, sc)
    root['kit'] = kind
    ctx.coll.objects.link(root)
    bpy.context.view_layer.update()
    ctx.root = root
    ctx.info = {'name': name, 'kind': kind}
    seed = spec.get('seed', 0)
    k['fn'](ctx, P, ctx.rng(kind, name, seed))
    ctx.root = None
    return root



# =========================================================================== plaster walls, keep, gate
def _bars(mb, key, x0, x1, z0, z1, y, n, w=0.07, d=0.07, axis='X'):
    """Vertical window bars (renji) between x0..x1 (or y along axis Y) on the plane y."""
    for i in range(n):
        x = x0 + (x1 - x0) * (i + 0.5) / n
        loc = (x, y, (z0 + z1) / 2) if axis == 'X' else (y, x, (z0 + z1) / 2)
        mb.box(key, (w, d, z1 - z0), loc=loc)


def _window(mb, key_bar, key_glow, key_frame, cx, z0, w, h, face_y, axis='X', bars=5, sign=-1, pr=None):
    """A barred castle window on a wall face: glowing (or dark) interior card, frame, bars. sign=-1 face -Y."""
    def at(x, y, z):
        return (x, y, z) if axis == 'X' else (y, x, z)
    y = face_y
    gsize = (w, 0.02, h) if axis == 'X' else (0.02, w, h)
    mb.box(key_glow, gsize, loc=at(cx, y + sign * 0.01, z0 + h / 2), pr=pr)
    fr = 0.12
    for zz in (z0 - fr / 2, z0 + h + fr / 2):
        mb.box(key_frame, (w + 2 * fr, 0.1, fr) if axis == 'X' else (0.1, w + 2 * fr, fr), loc=at(cx, y + sign * 0.05, zz))
    for xx in (cx - w / 2 - fr / 2, cx + w / 2 + fr / 2):
        mb.box(key_frame, (fr, 0.1, h) if axis == 'X' else (0.1, fr, h), loc=at(xx, y + sign * 0.05, z0 + h / 2))
    for i in range(bars):
        x = cx - w / 2 + w * (i + 0.5) / bars
        mb.box(key_bar, (0.075, 0.075, h) if axis == 'X' else (0.075, 0.075, h), loc=at(x, y + sign * 0.06, z0 + h / 2))


@piece('plaster_wall', length=12.0, height=2.5, thickness=0.45, footing=0.45, skirt=0.9, posts=1.8, cap=True,
       sama=4, sama_shape='tri', key='plaster', wood='wood_dark_z', stone='stone_dressed')
def plaster_wall(ctx, P, rnd):
    """Earthen castle wall (dobei): dressed-stone footing, black board skirt (shitami-itabari), white plaster
    panels between posts, a small tiled gable cap, triangle / square loopholes (sama). Runs along X."""
    L, H, t = P['length'], P['height'], P['thickness']
    mb = MB(ctx, ctx.info['name'], rnd)
    f = P['footing']
    if f > 0:
        x = -L / 2
        while x < L / 2 - 0.05:
            w = min(rnd.uniform(0.5, 1.0), L / 2 - x)
            for sy in (-1, 1):
                m = M4((x + w / 2, sy * (t / 2 - 0.08), f / 2), (0, 0, 0 if sy < 0 else 180))
                mb.stone(P['stone'], (w - 0.02, 0.36, f), m, rnd, square=0.26, bulge=0.04, chip=0.03)
            x += w
        mb.box('backfill', (L, t - 0.1, f), loc=(0, 0, f / 2))
    n = max(1, round(L / P['posts'])) if P['posts'] else 1
    bay = L / n
    for i in range(n):
        x = -L / 2 + bay * (i + 0.5)
        mb.box(P['key'], (bay, t, H - f), loc=(x, 0, f + (H - f) / 2), pr=rnd.random())
    sk = P['skirt']
    if sk > 0:
        for sy in (-1, 1):
            x = -L / 2
            while x < L / 2 - 0.01:
                w = min(0.24 + rnd.uniform(-0.03, 0.03), L / 2 - x)
                mb.box(P['wood'], (w - 0.006, 0.03, sk), loc=(x + w / 2, sy * (t / 2 + 0.015), f + sk / 2), pr=rnd.random())
                x += w
            mb.box('wood_dark', (L, 0.05, 0.06), loc=(0, sy * (t / 2 + 0.04), f + sk))
            for i in range(n + 1):
                mb.box('wood_dark', (0.06, 0.05, sk), loc=(-L / 2 + bay * i, sy * (t / 2 + 0.045), f + sk / 2))
    if P['posts']:
        for i in range(n + 1):
            for sy in (-1, 1):
                mb.box(P['wood'], (0.13, 0.04, H - f - sk), loc=(-L / 2 + bay * i, sy * (t / 2 + 0.02), f + sk + (H - f - sk) / 2))
    mb.box('wood_dark', (L, t + 0.08, 0.12), loc=(0, 0, H - 0.06))
    for k in range(P['sama']):
        x = -L / 2 + L * (k + 0.5) / max(1, P['sama'])
        z = f + sk + 0.45
        y = -t / 2 - 0.004
        if P['sama_shape'] == 'tri':
            mb.poly('window_dark', [(x - 0.13, y, z), (x + 0.13, y, z), (x, y, z + 0.22)])
        else:
            mb.poly('window_dark', [(x - 0.11, y, z), (x + 0.11, y, z), (x + 0.11, y, z + 0.2), (x - 0.11, y, z + 0.2)])
    if P['cap']:
        gable_roof(mb, L, t, pitch=30, overhang=0.32, z0=H, fascia='wood_dark', end_caps=True)
    mb.finish()


@piece('roof', width=8.0, depth=6.0, pitch=30.0, overhang=1.2, upturn=0.35, kind='hip', v_max=1.0, shachi=False,
       soffit='plaster', tile_w=0.3)
def roof(ctx, P, rnd):
    """Stand-alone tiled roof: kind 'hip' (yosemune, upturned corners, plaster eaves; v_max < 1 = pent skirt)
    or 'gable' (kirizuma). Eave at z = 0."""
    mb = MB(ctx, ctx.info['name'], rnd)
    if P['kind'] == 'gable':
        gable_roof(mb, P['width'], P['depth'], pitch=P['pitch'], overhang=P['overhang'], tile_w=P['tile_w'])
    else:
        hip_roof(mb, P['width'], P['depth'], pitch=P['pitch'], overhang=P['overhang'], upturn=P['upturn'],
                 v_max=P['v_max'], shachi='gold' if P['shachi'] else None, soffit=P['soffit'], tile_w=P['tile_w'])
    mb.finish()


def _storey_walls(mb, rnd, w, d, z0, z1, *, windows=1.0, win_h=1.0, win_z=None, lit=0.5, skirt=0.0, key='plaster',
                  wood='wood_dark_z', bands=True, sides=(0, 1, 2, 3), bars='plaster'):
    """One castle storey: plaster box, raised bands (nageshi), barred windows (some lit), optional black skirt."""
    mb.box(key, (w, d, z1 - z0), loc=(0, 0, (z0 + z1) / 2), pr=rnd.random())
    win_z = z0 + (z1 - z0) * 0.42 if win_z is None else win_z
    if bands:
        for zb in (win_z - 0.18, win_z + win_h + 0.2):
            mb.box(key, (w + 0.08, d + 0.08, 0.1), loc=(0, 0, zb))
    if skirt > 0:
        for k in range(4):
            ax = 'X' if k % 2 == 0 else 'Y'
            sign = -1 if k in (0, 3) else 1
            L = w if ax == 'X' else d
            off = (d if ax == 'X' else w) / 2 + 0.015
            x = -L / 2
            while x < L / 2 - 0.01:
                bw = min(0.26, L / 2 - x)
                loc = (x + bw / 2, sign * off, z0 + skirt / 2) if ax == 'X' else (sign * off, x + bw / 2, z0 + skirt / 2)
                mb.box(wood, (bw - 0.008, 0.03, skirt) if ax == 'X' else (0.03, bw - 0.008, skirt), loc=loc, pr=rnd.random())
                x += bw
    for k in sides:
        ax = 'X' if k % 2 == 0 else 'Y'
        sign = -1 if k in (0, 3) else 1
        L = w if ax == 'X' else d
        n = max(1, int(round(L / 3.0 * windows)))
        face = sign * ((d if ax == 'X' else w) / 2)
        for i in range(n):
            cx = -L / 2 + L * (i + 0.5) / n
            key_glow = 'window_glow' if rnd.random() < lit else 'window_dark'
            _window(mb, bars, key_glow, key, cx, win_z, min(1.3, L / n * 0.55), win_h, face, axis=ax, sign=sign, pr=rnd.random())


@piece('tenshu', base_w=17.0, base_d=14.0, base_h=7.0, storeys=4, storey_h=3.5, inset=1.45, pitch=27.0, overhang=1.5,
       upturn=0.55, windows=1.0, lit=0.55, gables=[1, 2], skirt=0.0, shachi=True, stone=0.8, style='uchikomi', batter=2.2)
def tenshu(ctx, P, rnd):
    """Castle keep (tenshu): battered stone base, stacked white plaster storeys stepping in, tiled pent roofs with
    upturned corners and white plaster eaves between them, triangular chidori gables, barred windows (a share
    glowing at night: material 'window_glow'), a hip top roof with golden shachihoko. Front faces -Y."""
    T = ishigaki_block(ctx, rnd, P['base_w'], P['base_d'], P['base_h'], batter=P['batter'], stone=P['stone'],
                       style=P['style'], name=ctx.info['name'] + '_base', top='stone_dark')
    walls = MB(ctx, ctx.info['name'] + '_walls', rnd)
    roofs = MB(ctx, ctx.info['name'] + '_roofs', rnd)
    w = P['base_w'] - 2 * T - 0.4
    d = P['base_d'] - 2 * T - 0.4
    z = P['base_h']
    n = P['storeys']
    o = P['overhang']
    sori = 1.35
    for i in range(n):
        top = i == n - 1
        wi, di = w - 2 * P['inset'] * i, d - 2 * P['inset'] * i
        sh = P['storey_h'] * (0.9 if top else 1.0)
        zb_ext = z - (0.0 if i == 0 else 1.2)
        zt = z + sh
        _storey_walls(walls, rnd, wi, di, zb_ext, zt, windows=P['windows'], win_z=z + sh * 0.35, win_h=min(1.1, sh * 0.32),
                      lit=P['lit'], skirt=P['skirt'] if not top else 0.0)
        ze = zt - 0.15
        if top:
            hip_roof(roofs, wi, di, pitch=P['pitch'] + 4, overhang=o * 0.95, upturn=P['upturn'], z0=ze,
                     shachi='gold' if P['shachi'] else None)
            break
        wn, dn = wi - 2 * P['inset'], di - 2 * P['inset']
        Do = di / 2 + o
        vmax = (Do - dn / 2) / Do
        rise = hip_roof(roofs, wi, di, pitch=P['pitch'], overhang=o, upturn=P['upturn'], z0=ze, v_max=vmax, ridge=False)
        z_meet = ze + rise * vmax ** sori
        if i in P['gables']:
            gw = min(wi * 0.42, 6.5)
            for sy in (-1, 1):
                yf = sy * (di / 2 + o * 0.25)
                vf = (Do - abs(yf)) / Do
                z0g = ze + rise * vf ** sori + 0.25
                Lg = abs(yf) - dn / 2 + 0.6
                yc = sy * (abs(yf) - Lg / 2)
                rg = gable_roof(roofs, Lg, gw, pitch=42, overhang=0.45, z0=z0g, axis='Y', offset=(0, yc, 0), fascia='plaster')
                tri_y = yf - sy * 0.15
                walls.poly('plaster', [(-gw / 2, tri_y, z0g - 0.25), (gw / 2, tri_y, z0g - 0.25), (0, tri_y, z0g + rg - 0.1)] if sy < 0 else
                           [(gw / 2, tri_y, z0g - 0.25), (-gw / 2, tri_y, z0g - 0.25), (0, tri_y, z0g + rg - 0.1)])
                walls.box('plaster', (gw, abs(yf) - dn / 2, z0g - 0.2 - ze + 0.5), loc=(0, sy * (dn / 2 + (abs(yf) - dn / 2) / 2), (z0g - 0.2 + ze - 0.5) / 2 + 0.25))
                walls.box('gold', (0.35, 0.06, 0.45), loc=(0, tri_y + sy * 0.05, z0g + rg - 0.55))
        z = z_meet
    walls.finish()
    roofs.finish()


@piece('yaguramon', width=16.0, passage=5.0, depth=7.0, base_h=4.2, upper_h=3.4, open=0.25, pitch=28.0, overhang=1.3,
       stone=0.6, lit=0.35, skirt=1.1, shachi=False, batter=1.0)
def yaguramon(ctx, P, rnd):
    """Turret gate (yaguramon): two battered stone blocks, a plaster gatehouse storey bridging the passage, heavy
    plank doors with iron studs and straps (open = 0..1), posts and a lintel beam, hip roof. Passage along Y."""
    W, Pw, D, Hb = P['width'], P['passage'], P['depth'], P['base_h']
    bw = (W - Pw) / 2
    st = MB(ctx, ctx.info['name'] + '_stones', rnd)
    bf = MB(ctx, ctx.info['name'] + '_core', rnd)
    T = 0
    for sx in (-1, 1):
        T = ishigaki_block(ctx, rnd, bw, D, Hb, batter=P['batter'], stone=P['stone'], style='uchikomi',
                           at=(sx * (Pw / 2 + bw / 2), 0, 0), mb=st, bf=bf, top='stone_dark')
    st.finish()
    bf.finish()
    mb = MB(ctx, ctx.info['name'] + '_house', rnd)
    wu, du = W - 2 * T - 0.2, D - 2 * T - 0.2
    z0 = Hb
    mb.box('wood_dark', (Pw + 2 * T + 1.0, du + 0.2, 0.55), loc=(0, 0, z0 - 0.2))
    _storey_walls(mb, rnd, wu, du, z0, z0 + P['upper_h'], windows=0.8, win_h=0.9, lit=P['lit'], skirt=P['skirt'], sides=(0, 2))
    hip_roof(mb, wu, du, pitch=P['pitch'], overhang=P['overhang'], upturn=0.4, z0=z0 + P['upper_h'] - 0.12,
             shachi='gold' if P['shachi'] else None)
    yd = du / 2 - 0.3
    ph = Hb - 0.45
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box('wood_dark_z', (0.5, 0.5, ph), loc=(sx * (Pw / 2 - 0.1), sy * yd, ph / 2), bevel=0.02)
        mb.box('wood_dark_z', (0.42, 0.42, ph), loc=(sx * (Pw / 2 - 0.1), 0, ph / 2), bevel=0.02)
    for sy in (-1, 1):
        mb.box('wood_dark', (Pw + 0.6, 0.45, 0.6), loc=(0, sy * yd, ph + 0.05), bevel=0.02)
    mb.box('wood_dark', (Pw, du, 0.1), loc=(0, 0, ph - 0.05))
    # doors on the middle posts, swinging toward +Y
    leaf = Pw / 2 - 0.35
    dh = ph - 0.2
    for sx in (-1, 1):
        hinge = Vector((sx * (Pw / 2 - 0.35), 0.25, 0))
        ang = -sx * P['open'] * 85
        R = M4(hinge, (0, 0, ang))
        nb = 6
        for b in range(nb):
            x = -sx * (leaf * (b + 0.5) / nb)
            mb.box('wood_dark_z', (leaf / nb - 0.01, 0.12, dh), loc=(x, 0, dh / 2 + 0.05), matrix=R, pr=rnd.random())
        for zz in (0.5, dh * 0.5, dh - 0.4):
            mb.box('iron', (leaf, 0.03, 0.12), loc=(-sx * leaf / 2, -0.075, zz), matrix=R)
            for k in range(8):
                mb.cyl('iron', 0.035, 0.02, 0.04, 6, loc=(-sx * leaf * (k + 0.5) / 8, -0.095, zz), rot=(90, 0, 0), matrix=R)
        for rr in range(5):
            for k in range(5):
                mb.cyl('iron', 0.03, 0.018, 0.035, 6, loc=(-sx * leaf * (k + 0.5) / 5, -0.075, 0.9 + rr * (dh - 1.6) / 4), rot=(90, 0, 0), matrix=R)
    mb.finish()


# =========================================================================== floors, mats, screens, rooms
@piece('floor_planks', width=10.0, depth=8.0, plank=0.21, gap=0.004, thickness=0.05, along='X', key='wood_floor',
       min_len=1.8, max_len=4.0, warp=0.0025)
def floor_planks(ctx, P, rnd):
    """Board floor: staggered planks (own tone and grain each), hairline gaps, slight cupping; top at z = 0."""
    W, D, pw = P['width'], P['depth'], P['plank']
    key = P['key']
    if P['along'] == 'Y' and key == 'wood_floor':
        key = 'wood_floor_y'
    mb = MB(ctx, ctx.info['name'], rnd)
    L1, L2 = (W, D) if P['along'] == 'X' else (D, W)
    n = int(math.ceil(L2 / pw))
    for r in range(n):
        c2 = -L2 / 2 + pw * (r + 0.5)
        x = -L1 / 2 - rnd.uniform(0, P['max_len'])
        while x < L1 / 2:
            ln = rnd.uniform(P['min_len'], P['max_len'])
            a, b = max(x, -L1 / 2), min(x + ln, L1 / 2)
            if b - a > 0.05:
                c1 = (a + b) / 2
                dz = rnd.uniform(-P['warp'], P['warp'])
                size = (b - a - P['gap'], pw - P['gap'], P['thickness'])
                loc = (c1, c2, -P['thickness'] / 2 + dz) if P['along'] == 'X' else (c2, c1, -P['thickness'] / 2 + dz)
                if P['along'] != 'X':
                    size = (size[1], size[0], size[2])
                mb.box(key, size, loc=loc, rot=(rnd.uniform(-0.15, 0.15), rnd.uniform(-0.15, 0.15), 0), bevel=0.003)
            x += ln
    mb.box('backfill', (W, D, 0.02), loc=(0, 0, -P['thickness'] - 0.005))
    mb.finish()


@piece('tatami', nx=4, ny=2, mat_l=1.82, mat_w=0.91, thickness=0.055, key='tatami', border='tatami_border', offset=True)
def tatami(ctx, P, rnd):
    """Tatami mats (long side along X), dark cloth borders on the long edges; rows offset like a running bond."""
    mb = MB(ctx, ctx.info['name'], rnd)
    L, Wm, t = P['mat_l'], P['mat_w'], P['thickness']
    tw, td = P['nx'] * L, P['ny'] * Wm
    for j in range(P['ny']):
        y = -td / 2 + Wm * (j + 0.5)
        shift = (L / 2 if (P['offset'] and j % 2) else 0)
        for i in range(P['nx'] + (1 if shift else 0)):
            a = -tw / 2 + L * i - shift
            b = a + L
            a, b = max(a, -tw / 2), min(b, tw / 2)
            if b - a < 0.1:
                continue
            x = (a + b) / 2
            mb.box(P['key'], (b - a - 0.006, Wm - 0.006, t), loc=(x, y, t / 2), bevel=0.006)
            for sy in (-1, 1):
                mb.box(P['border'], (b - a - 0.006, 0.035, t + 0.002), loc=(x, y + sy * (Wm / 2 - 0.02), t / 2 + 0.001))
    mb.finish()


def shoji_panels(mb, rnd, x0, x1, z0, z1, y, *, panels=2, cols=3, rows=7, koshi=0.3, frame='wood_light',
                 paper='shoji', axis='X', open_=0.0, sign=1):
    """Sliding shoji between x0..x1 on the plane y (or along Y): frames, kumiko lattice, washi behind (side +sign)."""
    def at(a, b, c):
        return (a, b, c) if axis == 'X' else (b, a, c)

    def sz(a, b, c):
        return (a, b, c) if axis == 'X' else (b, a, c)
    pw = (x1 - x0) / panels
    for k in range(panels):
        xo = x0 + pw * k + (pw * open_ if k % 2 else 0)
        yo = y + (0.035 if k % 2 else 0) * sign
        cx = xo + pw / 2
        fr = 0.035
        for xx in (xo + fr / 2, xo + pw - fr / 2):
            mb.box(frame, sz(fr, 0.03, z1 - z0), loc=at(xx, yo, (z0 + z1) / 2))
        for zz in (z0 + fr / 2, z1 - fr / 2, z0 + koshi):
            mb.box(frame, sz(pw, 0.03, fr), loc=at(cx, yo, zz))
        if koshi > 0:
            mb.box('wood_light', sz(pw - 2 * fr, 0.015, koshi - fr), loc=at(cx, yo, z0 + (koshi + fr) / 2 - fr / 2), pr=rnd.random())
        za, zb = z0 + koshi + fr / 2, z1 - fr
        for c in range(1, cols):
            mb.box(frame, sz(0.012, 0.02, zb - za), loc=at(xo + pw * c / cols, yo, (za + zb) / 2))
        for r in range(1, rows):
            mb.box(frame, sz(pw - 2 * fr, 0.02, 0.012), loc=at(cx, yo, za + (zb - za) * r / rows))
        py = yo + sign * 0.013
        pts = [at(xo + fr, py, za), at(xo + pw - fr, py, za), at(xo + pw - fr, py, zb), at(xo + fr, py, zb)]
        mb.poly(paper, pts if sign > 0 else pts[::-1], pr=rnd.random())


@piece('shoji', width=3.6, height=1.9, panels=4, cols=3, rows=7, koshi=0.3, frame='wood_light', paper='shoji',
       backlight=0.0, backlight_color=(1.0, 0.78, 0.5), backlight_dist=0.8, open=0.0, sill=True)
def shoji(ctx, P, rnd):
    """Shoji screen: sliding panels of kumiko lattice with washi behind (+Y side). The paper is translucent:
    a lamp behind (`backlight` W, an area light the screen's size) makes it glow and throws the lattice shadow."""
    mb = MB(ctx, ctx.info['name'], rnd)
    W, H = P['width'], P['height']
    shoji_panels(mb, rnd, -W / 2, W / 2, 0.02, H, 0.0, panels=P['panels'], cols=P['cols'], rows=P['rows'], koshi=P['koshi'],
                 frame=P['frame'], paper=P['paper'], open_=P['open'])
    if P['sill']:
        mb.box('wood_dark', (W + 0.1, 0.12, 0.04), loc=(0, 0.02, 0.0))
        mb.box('wood_dark', (W + 0.1, 0.12, 0.08), loc=(0, 0.02, H + 0.04))
    mb.finish()
    if P['backlight'] > 0:
        ctx.light('AREA', (0, P['backlight_dist'], H / 2), P['backlight'], P['backlight_color'], size=(W, H),
                  look=(0, -5, H / 2), name=ctx.info['name'] + '_backlight')


@piece('room', width=12.0, depth=10.0, height=3.4, post=1.82, walls={'back': 'plaster', 'left': 'renji', 'right': 'shoji', 'front': 'open'},
       wainscot=0.9, window_z=2.0, window_h=0.75, beams=True, ceiling=True, alcove=True, post_key='wood_post',
       beam_key='wood_dark', wall_key='plaster', board_key='wood', roof=True, shoji_h=2.1)
def room(ctx, P, rnd):
    """Timber-frame hall (dojo, interior): posts on a grid along the walls, nageshi beams, walls per side
    ('plaster', 'renji' = plaster with a high barred window band that lets light shafts in, 'shoji', 'wood',
    'open'), wainscot boards, a coffered board ceiling with heavy cross beams, an alcove (tokonoma) with a scroll
    on the back wall, and a closed roof slab. Floor not included (use floor_planks). Front = -Y."""
    W, D, H = P['width'], P['depth'], P['height']
    mb = MB(ctx, ctx.info['name'], rnd)
    sides = {'front': (-D / 2, 'X', W, -1), 'back': (D / 2, 'X', W, 1), 'left': (-W / 2, 'Y', D, -1), 'right': (W / 2, 'Y', D, 1)}
    wt = 0.14
    for side, (pos, ax, L, sign) in sides.items():
        style = P['walls'].get(side, 'open')
        n = max(1, round(L / P['post']))
        bay = L / n

        def at(a, b, c, ax=ax):
            return (a, b, c) if ax == 'X' else (b, a, c)

        def sz(a, b, c, ax=ax):
            return (a, b, c) if ax == 'X' else (b, a, c)
        for i in range(n + 1):
            mb.box(P['post_key'], (0.16, 0.16, H), loc=at(-L / 2 + bay * i, pos, H / 2), bevel=0.01)
        mb.box(P['beam_key'], sz(L + 0.2, 0.2, 0.28), loc=at(0, pos, H - 0.14))
        if style != 'open':
            mb.box(P['beam_key'], sz(L, 0.19, 0.14), loc=at(0, pos, P['window_z'] + P['window_h'] + 0.07))
        for i in range(n):
            a = -L / 2 + bay * i + 0.08
            b = a + bay - 0.16
            c = (a + b) / 2
            if style in ('plaster', 'renji', 'wood'):
                ztop = P['window_z'] if style == 'renji' else H - 0.28
                if P['alcove'] and side == 'back' and abs(c) < bay * 0.6:
                    ztop = H - 0.28
                mb.box(P['board_key'], sz(b - a, wt, P['wainscot']), loc=at(c, pos, P['wainscot'] / 2), pr=rnd.random())
                if style == 'wood':
                    mb.box(P['board_key'], sz(b - a, wt, ztop - P['wainscot']), loc=at(c, pos, (ztop + P['wainscot']) / 2), pr=rnd.random())
                else:
                    mb.box(P['wall_key'], sz(b - a, wt * 0.9, ztop - P['wainscot']), loc=at(c, pos, (ztop + P['wainscot']) / 2), pr=rnd.random())
                if style == 'renji' and ztop < H - 0.3:
                    z1 = P['window_z'] + P['window_h']
                    _bars(mb, 'wood_post', a, b, P['window_z'], z1, pos, 5, 0.05, 0.07, axis=ax)
                    mb.box(P['wall_key'], sz(b - a, wt * 0.9, H - 0.28 - z1 - 0.14), loc=at(c, pos, (H - 0.28 + z1 + 0.14) / 2), pr=rnd.random())
                    mb.box(P['beam_key'], sz(b - a, 0.17, 0.06), loc=at(c, pos, P['window_z'] - 0.03))
            elif style == 'shoji':
                zs = P['shoji_h']
                shoji_panels(mb, rnd, a, b, 0.02, zs, pos, panels=2, cols=3, rows=8, axis=ax, sign=sign)
                mb.box('wood_dark', sz(b - a, 0.12, 0.05), loc=at(c, pos, zs + 0.025))
                shoji_panels(mb, rnd, a, b, zs + 0.05, H - 0.3, pos, panels=1, cols=8, rows=2, koshi=0.0, axis=ax, sign=sign)
    if P['ceiling']:
        x = -W / 2
        while x < W / 2 - 0.01:
            bw = min(0.45, W / 2 - x)
            mb.box('wood_light', (bw - 0.004, D, 0.02), loc=(x + bw / 2, 0, H + 0.01), pr=rnd.random())
            x += bw
        for k in range(int(D / 0.45) + 1):
            mb.box('wood_dark', (W, 0.04, 0.05), loc=(0, -D / 2 + k * 0.45, H - 0.02))
    if P['beams']:
        n = max(1, round(W / (P['post'] * 2)))
        for k in range(1, n):
            mb.box(P['beam_key'], (0.3, D + 0.2, 0.42), loc=(-W / 2 + W * k / n, 0, H - 0.21), bevel=0.015)
    if P['roof']:
        mb.box('backfill', (W + 1, D + 1, 0.3), loc=(0, 0, H + 0.25))
    if P['alcove']:
        aw = min(3.6, W * 0.3)
        mb.box('lacquer_black', (aw, 0.1, 0.16), loc=(0, D / 2 - 0.85, 0.08))
        mb.box('wood_light', (aw, 0.8, 0.14), loc=(0, D / 2 - 0.45, 0.07), pr=0.3)
        mb.box('paper', (0.62, 0.012, 1.7), loc=(0, D / 2 - 0.09, 1.55))
        mb.box('cloth_dark', (0.74, 0.01, 1.95), loc=(0, D / 2 - 0.08, 1.5))
        for zz in (0.55, 2.47):
            mb.cyl('lacquer_black', 0.02, 0.02, 0.82, 8, loc=(0, D / 2 - 0.1, zz), rot=(0, 90, 0))
    mb.finish()


# =========================================================================== shrine and garden pieces
@piece('torii', height=5.2, span=4.0, pillar_r=0.24, key='lacquer_red', top='lacquer_black', lean=2.0, over=1.2, upcurve=0.35, plaque=True)
def torii(ctx, P, rnd):
    """Torii (myojin style): leaning pillars on black bases, nuki tie beam through them, curved kasagi with
    upturned ends over the shimaki, centre strut and plaque. Lacquer with worn edges."""
    mb = MB(ctx, ctx.info['name'], rnd)
    H, S, r = P['height'], P['span'], P['pillar_r']
    lean = math.radians(P['lean'])
    for sx in (-1, 1):
        base = Vector((sx * S / 2, 0, 0))
        top = Vector((sx * (S / 2 - H * math.tan(lean)), 0, H - 0.3))
        mid = (base + top) / 2
        q = (top - base).normalized().to_track_quat('Z', 'Y').to_matrix()
        mb.cyl(P['key'], r, r * 0.88, (top - base).length, 16, loc=mid, rot=q)
        mb.cyl(P['top'], r * 1.25, r * 1.18, 0.5, 16, loc=(sx * S / 2, 0, 0.25))
    zn = H * 0.74
    mb.box(P['key'], (S + 2 * P['over'] * 0.6, 0.2, 0.32), loc=(0, 0, zn), bevel=0.02)
    half = S / 2 + P['over']
    n = 18
    for layer, (key, w, h, dz) in enumerate(((P['key'], 0.34, 0.26, 0.0), (P['top'], 0.42, 0.32, 0.28))):
        pts = []
        for i in range(n + 1):
            x = -half + 2 * half * i / n
            z = H - 0.12 + dz + P['upcurve'] * (abs(x) / half) ** 2.6
            pts.append(Vector((x, 0, z)))
        for i in range(n):
            beam_between(mb, key, pts[i], pts[i + 1], w, h)
    mb.box(P['key'], (0.22, 0.18, H - 0.12 - zn - 0.16), loc=(0, 0, (H - 0.12 + zn) / 2))
    if P['plaque']:
        mb.box('lacquer_black', (0.55, 0.08, 0.85), loc=(0, -0.06, (H - 0.12 + zn) / 2), bevel=0.02)
        mb.box('gold', (0.38, 0.01, 0.62), loc=(0, -0.105, (H - 0.12 + zn) / 2))
    mb.finish()


@piece('toro', height=2.2, lit=True, energy=14.0, color=(1.0, 0.52, 0.2), key='stone_lantern', paper='lantern_paper', moss=None)
def toro(ctx, P, rnd):
    """Kasuga stone lantern (toro): hexagonal base, round pillar with a collar, platform, a firebox of six posts
    with paper panels (a warm point light inside shines through them), hexagonal roof with curled tips, finial."""
    mb = MB(ctx, ctx.info['name'], rnd)
    k = P['height'] / 2.2
    S = lambda *v: tuple(c * k for c in v)  # noqa: E731
    key = P['key']
    mb.cyl(key, 0.40 * k, 0.36 * k, 0.16 * k, 6, loc=S(0, 0, 0.08))
    mb.cyl(key, 0.30 * k, 0.22 * k, 0.12 * k, 6, loc=S(0, 0, 0.22))
    mb.cyl(key, 0.11 * k, 0.10 * k, 0.78 * k, 12, loc=S(0, 0, 0.66))
    mb.cyl(key, 0.14 * k, 0.14 * k, 0.06 * k, 12, loc=S(0, 0, 0.66))
    mb.cyl(key, 0.20 * k, 0.35 * k, 0.17 * k, 6, loc=S(0, 0, 1.135))
    for i in range(6):
        a = math.pi / 3 * i
        mb.box(key, S(0.06, 0.06, 0.38), loc=S(0.215 * math.cos(a), 0.215 * math.sin(a), 1.41), rot=(0, 0, math.degrees(a)))
        a0, a1 = a + 0.12, a + math.pi / 3 - 0.12
        r = 0.19 * k
        pts = [(r * math.cos(a0), r * math.sin(a0), 1.25 * k), (r * math.cos(a1), r * math.sin(a1), 1.25 * k),
               (r * math.cos(a1), r * math.sin(a1), 1.58 * k), (r * math.cos(a0), r * math.sin(a0), 1.58 * k)]
        mb.poly(P['paper'], pts[::-1], pr=rnd.random())
    mb.cyl(key, 0.26 * k, 0.26 * k, 0.04 * k, 6, loc=S(0, 0, 1.23))
    mb.cyl(key, 0.50 * k, 0.12 * k, 0.24 * k, 6, loc=S(0, 0, 1.73))
    mb.cyl(key, 0.50 * k, 0.48 * k, 0.05 * k, 6, loc=S(0, 0, 1.62))
    for i in range(6):
        a = math.pi / 3 * i
        mb.box(key, S(0.12, 0.07, 0.09), loc=S(0.5 * math.cos(a), 0.5 * math.sin(a), 1.68), rot=(0, -35, math.degrees(a)))
    mb.cyl(key, 0.08 * k, 0.1 * k, 0.08 * k, 8, loc=S(0, 0, 1.89))
    res = bmesh.ops.create_icosphere(mb.bm, subdivisions=1, radius=0.085 * k, matrix=M4(S(0, 0, 2.0), None, (1, 1, 1.25)))
    mb.tag(mb.faces_of(res['verts']), key)
    mb.finish()
    if P['lit']:
        ctx.light('POINT', S(0, 0, 1.42), P['energy'], P['color'], size=0.05 * k, name=ctx.info['name'] + '_flame')


@piece('stairs', width=4.0, steps=8, rise=0.17, run=0.34, key='stone_dressed', cheeks=True, cheek_key='stone')
def stairs(ctx, P, rnd):
    """Stone steps climbing toward +Y (first riser at y = 0): each step of 2-3 dressed blocks, low stone cheeks."""
    mb = MB(ctx, ctx.info['name'], rnd)
    W = P['width']
    for k in range(P['steps']):
        z0 = k * P['rise']
        y0 = k * P['run']
        n = rnd.choice((2, 3))
        x = -W / 2
        cuts = sorted(rnd.uniform(-W / 2 + 0.6, W / 2 - 0.6) for _ in range(n - 1)) + [W / 2]
        for c in cuts:
            w = c - x
            m = M4((x + w / 2, y0 + P['run'] * 0.55, z0 + P['rise'] / 2), (0, 0, rnd.uniform(-0.6, 0.6)))
            mb.stone(P['key'], (w - 0.025, P['run'] * 1.15, P['rise']), m, rnd, square=0.22, bulge=0.02, chip=0.03, flat_back=False)
            x = c
        mb.box('backfill', (W - 0.05, P['run'], max(0.01, z0)), loc=(0, y0 + P['run'] / 2, z0 / 2))
    if P['cheeks']:
        Ltot = P['steps'] * P['run']
        Htot = P['steps'] * P['rise']
        for sx in (-1, 1):
            n = max(2, int(Ltot / 0.7))
            for i in range(n):
                y = Ltot * (i + 0.5) / n
                h = Htot * (i + 1) / n + 0.25
                m = M4((sx * (W / 2 + 0.25), y, h / 2), (0, 0, 90))
                mb.stone(P['cheek_key'], (Ltot / n - 0.03, 0.5, h), m, rnd, square=0.3, bulge=0.04)
    mb.finish()


@piece('bridge', length=9.0, width=2.2, arch=1.2, key='wood_aged', rail_key='lacquer_red', rails=True, posts=6, piers=True)
def bridge(ctx, P, rnd):
    """Arched wooden bridge (taikobashi) along X: deck planks across the arch, stringers, red-lacquer rails on
    posts with onion finials at the ends, pier posts and cross beams under it."""
    mb = MB(ctx, ctx.info['name'], rnd)
    L, Wd, A = P['length'], P['width'], P['arch']

    def zf(x):
        return A * (1 - (2 * x / L) ** 2)

    def slope(x):
        return -8 * A * x / (L * L)
    x = -L / 2
    while x < L / 2:
        pw = 0.22
        xc = x + pw / 2
        mb.box(P['key'], (pw - 0.012, Wd, 0.06), loc=(xc, 0, zf(xc) - 0.03), rot=(0, -math.degrees(math.atan(slope(xc))), 0), bevel=0.004)
        x += pw
    n = 20
    for sy in (-0.8, 0.0, 0.8):
        pts = [Vector((-L / 2 + L * i / n, sy * Wd / 2, zf(-L / 2 + L * i / n) - 0.2)) for i in range(n + 1)]
        for i in range(n):
            beam_between(mb, 'wood_aged', pts[i], pts[i + 1], 0.16, 0.24)
    if P['rails']:
        for sy in (-1, 1):
            y = sy * (Wd / 2 - 0.06)
            xs = [-L / 2 + L * i / (P['posts'] - 1) for i in range(P['posts'])]
            for i, xp in enumerate(xs):
                mb.box(P['rail_key'], (0.13, 0.13, 1.0), loc=(xp, y, zf(xp) + 0.45))
                if i in (0, len(xs) - 1):
                    res = bmesh.ops.create_icosphere(mb.bm, subdivisions=1, radius=0.1, matrix=M4((xp, y, zf(xp) + 1.05), None, (1, 1, 1.3)))
                    mb.tag(mb.faces_of(res['verts']), 'gold')
            for hz, (w, h) in ((0.88, (0.1, 0.08)), (0.45, (0.06, 0.06))):
                pts = [Vector((-L / 2 + L * i / n, y, zf(-L / 2 + L * i / n) + hz)) for i in range(n + 1)]
                for i in range(n):
                    beam_between(mb, P['rail_key'], pts[i], pts[i + 1], w, h)
    if P['piers']:
        for xp in (-L * 0.28, L * 0.28):
            for sy in (-1, 1):
                mb.box('wood_aged', (0.2, 0.2, zf(xp) + 1.6), loc=(xp, sy * Wd * 0.4, (zf(xp) - 1.6) / 2), bevel=0.01)
            mb.box('wood_aged', (0.18, Wd, 0.18), loc=(xp, 0, zf(xp) - 0.4))
    mb.finish()


@piece('ground', width=40.0, depth=40.0, key='gravel', res=48, bumps=0.04, bump_scale=0.35, z=0.0, edge_rise=0.0)
def ground(ctx, P, rnd):
    """Ground plane with gentle bumps (gravel, earth, sand, forest_floor, moss...). `edge_rise` lifts the far
    edges (a soft berm that hides the horizon line)."""
    mb = MB(ctx, ctx.info['name'], rnd)
    W, D = P['width'], P['depth']
    sd = Vector((rnd.uniform(0, 99), rnd.uniform(0, 99), 0))

    def f(u, v):
        x, y = (u - 0.5) * W, (v - 0.5) * D
        z = P['z'] + noise.noise(Vector((x, y, 0)) * P['bump_scale'] + sd) * P['bumps']
        if P['edge_rise']:
            e = max(abs(2 * u - 1), abs(2 * v - 1))
            z += P['edge_rise'] * max(0.0, (e - 0.7) / 0.3) ** 2
        return (x, y, z)
    mb.grid(P['key'], f, P['res'], P['res'])
    ob = mb.finish(smooth=True)
    return ob


@piece('paving', length=10.0, width=2.6, key='stone_dressed', height=0.05, along='Y')
def paving(ctx, P, rnd):
    """Stone-slab path (ishidatami): irregular dressed slabs in rows with joints, slightly proud of the ground."""
    mb = MB(ctx, ctx.info['name'], rnd)
    L, Wd = P['length'], P['width']
    y = -L / 2
    while y < L / 2:
        rl = min(rnd.uniform(0.45, 0.85), L / 2 - y)
        x = -Wd / 2
        while x < Wd / 2 - 0.05:
            w = min(rnd.uniform(0.45, 1.1), Wd / 2 - x)
            cx, cy = x + w / 2, y + rl / 2
            loc = (cx, cy, P['height'] - 0.07) if P['along'] == 'Y' else (cy, cx, P['height'] - 0.07)
            size = (w - 0.03, rl - 0.03, 0.14) if P['along'] == 'Y' else (rl - 0.03, w - 0.03, 0.14)
            mb.stone(P['key'], size, M4(loc, (0, 0, rnd.uniform(-1, 1))), rnd, square=0.2, bulge=0.0, chip=0.025, flat_back=False)
            x += w
        y += rl
    mb.finish()


# =========================================================================== nature
def _scatter(rnd, W, D, count, min_d, ok, tries=40):
    pts = []
    for _ in range(count):
        for _t in range(tries):
            p = (rnd.uniform(-W / 2, W / 2), rnd.uniform(-D / 2, D / 2))
            if ok(p) and all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > min_d * min_d for q in pts):
                pts.append(p)
                break
    return pts


def _leaf(mb, key, base, direction, length, width, side, pr):
    """One folded leaf: a diamond with a raised mid-rib crease (four triangles)."""
    d = direction.normalized()
    s = side.normalized()
    up = d.cross(s).normalized()
    tip = base + d * length
    mid = base + d * length * 0.4
    l, r = mid + s * width, mid - s * width
    rib = mid + up * width * 0.35
    for tri in ((base, l, rib), (rib, l, tip), (base, rib, r), (rib, tip, r)):
        mb.poly(key, tri, pr=pr)


@piece('bamboo_grove', width=20.0, depth=14.0, count=150, height=[9.0, 15.0], radius=[0.04, 0.085], lean=5.0,
       leaves=1.0, leaf_size=1.0, clear=[], path=None, min_dist=0.35, key='bamboo')
def bamboo_grove(ctx, P, rnd):
    """Moso bamboo grove: tall leaning culms (8-sided, tapering, own tone each) with node rings, twigs in the
    upper half carrying sprays of folded leaves. Keeps clear of the fighter marks, of `clear` [[x, y, r], ...]
    and of a `path` [[x0, y0], [x1, y1], width] (local)."""
    W, D = P['width'], P['depth']
    path = P['path']

    def ok(p):
        if not ctx.is_clear(p, 0.5):
            return False
        for x, y, r in P['clear']:
            if math.hypot(p[0] - x, p[1] - y) < r:
                return False
        if path:
            (x0, y0), (x1, y1), pw = path
            ax, ay = x1 - x0, y1 - y0
            t = max(0, min(1, ((p[0] - x0) * ax + (p[1] - y0) * ay) / (ax * ax + ay * ay)))
            if math.hypot(p[0] - (x0 + ax * t), p[1] - (y0 + ay * t)) < pw / 2:
                return False
        return True
    pts = _scatter(rnd, W, D, P['count'], P['min_dist'], ok)
    culms = MB(ctx, ctx.info['name'] + '_culms', rnd)
    leaves = MB(ctx, ctx.info['name'] + '_leaves', rnd)
    for (x, y) in pts:
        h = rnd.uniform(*P['height'])
        r0 = rnd.uniform(*P['radius'])
        lean = math.radians(rnd.uniform(0, P['lean']))
        az = rnd.uniform(0, 2 * math.pi)
        ld = Vector((math.cos(az), math.sin(az), 0))
        pr = rnd.random()
        seg = rnd.uniform(0.28, 0.4)
        n = int(h / seg)
        pts3, rad = [], []
        for i in range(n + 1):
            t = i / n
            z = h * t
            off = ld * (math.sin(lean) * z + 0.6 * math.sin(lean) * h * t * t)
            pts3.append(Vector((x, y, 0)) + off + Vector((0, 0, z)))
            rad.append(r0 * (1.0 - 0.55 * t))
        culms.tube(P['key'], pts3, rad, segs=8, pr=pr, cap=True)
        for i in range(1, n, 1):
            p, q = pts3[i], pts3[i + 1] if i + 1 <= n else pts3[i]
            culms.tube('bamboo_node', [p - (q - p).normalized() * 0.012, p + (q - p).normalized() * 0.012], [rad[i] * 1.09] * 2, segs=8, pr=pr, cap=False)
        if P['leaves'] <= 0:
            continue
        k0 = int(n * rnd.uniform(0.5, 0.62))
        for i in range(k0, n, max(1, int(2 / P['leaves']))):
            p = pts3[i]
            for side in (1, -1):
                if rnd.random() > 0.8:
                    continue
                a = az + side * math.pi / 2 + rnd.uniform(-0.8, 0.8) + i
                dirv = Vector((math.cos(a), math.sin(a), rnd.uniform(0.2, 0.7))).normalized()
                tl = rnd.uniform(0.5, 1.2) * (1.2 - (i / n) * 0.6)
                end = p + dirv * tl
                culms.tube('bamboo_node', [p, end], [0.008, 0.004], segs=3, pr=pr, cap=False)
                for kk in range(int(rnd.randint(5, 9) * max(1.0, P['leaves'] / 1.5))):
                    b = p.lerp(end, rnd.uniform(0.35, 1.0))
                    ang = rnd.uniform(0, 2 * math.pi)
                    dd = (dirv * 0.6 + Vector((math.cos(ang), math.sin(ang), -rnd.uniform(0.6, 1.4)))).normalized()
                    sd = dd.cross(Vector((0, 0, 1)))
                    if sd.length < 1e-3:
                        sd = Vector((1, 0, 0))
                    ls = P['leaf_size']
                    _leaf(leaves, 'bamboo_leaf', b, dd, rnd.uniform(0.16, 0.26) * ls, rnd.uniform(0.018, 0.03) * ls, sd, rnd.random())
    culms.finish()
    if P['leaves'] > 0:
        leaves.finish()


def _pad(mb, key, c, r, rnd, flat=0.38, tufts=1.0):
    """Cloud-pruned pine pad: a faceted flattened lump plus a bristle of needle tufts on top."""
    m = M4(c, (0, 0, rnd.uniform(0, 360)), (r, r * rnd.uniform(0.7, 0.95), r * flat))
    res = bmesh.ops.create_icosphere(mb.bm, subdivisions=2, radius=1.0, matrix=m)
    sd = Vector((rnd.uniform(0, 50),) * 3)
    for v in res['verts']:
        v.co += (v.co - Vector(c)).normalized() * noise.noise(v.co * 1.7 + sd) * r * 0.22
    mb.tag(mb.faces_of(res['verts']), key)
    for _ in range(int(r * r * 14 * tufts)):
        a = rnd.uniform(0, 2 * math.pi)
        rr = math.sqrt(rnd.random()) * r * 0.95
        p = Vector(c) + Vector((math.cos(a) * rr, math.sin(a) * rr * 0.85, r * flat * (0.55 - (rr / r) ** 2 * 0.55)))
        nrm = Vector((math.cos(a) * rr / r, math.sin(a) * rr / r, 1.0)).normalized()
        q = nrm.to_track_quat('Z', 'Y').to_matrix()
        mb.cyl(key, 0.11, 0.0, rnd.uniform(0.18, 0.32), 5, matrix=Matrix.Translation(p) @ q.to_4x4())


@piece('pine', height=7.0, spread=4.5, lean=18.0, lean_dir=-90.0, pads=6, pad_size=1.3, key='pine_needle', bark='bark')
def pine(ctx, P, rnd):
    """Japanese black pine (kuromatsu), garden-pruned: a leaning, kinked trunk with plated bark, crooked branches
    ending in flat cloud pads of needles. lean_dir = compass degrees of the lean (0 = +X)."""
    H = P['height']
    tr = MB(ctx, ctx.info['name'] + '_trunk', rnd)
    nd = MB(ctx, ctx.info['name'] + '_needles', rnd)
    la = math.radians(P['lean_dir'])
    ld = Vector((math.cos(la), math.sin(la), 0))
    lean = math.radians(P['lean'])
    pts, rad = [], []
    n = 9
    for i in range(n + 1):
        t = i / n
        z = H * 0.85 * t
        p = Vector((0, 0, z)) + ld * (math.sin(lean) * z * (0.6 + 0.6 * t)) + \
            Vector((math.sin(t * 7 + rnd.random()) * 0.25, math.cos(t * 5) * 0.2, 0)) * (t > 0)
        pts.append(p)
        rad.append(0.34 * (H / 7) * (1 - 0.75 * t) + 0.03)
    tr.tube(P['bark'], pts, rad, segs=9, pr=0.4)
    tr.tube(P['bark'], [pts[0] - Vector((0, 0, 0.3)), pts[0] + Vector((0, 0, 0.25))], [rad[0] * 1.6, rad[0] * 1.05], segs=9, cap=False)
    _pad(nd, P['key'], pts[-1] + Vector((0, 0, 0.4)), P['pad_size'] * 1.1, rnd)
    for k in range(P['pads']):
        t = 0.38 + 0.55 * (k / max(1, P['pads'] - 1))
        i = min(n - 1, int(t * n))
        base = pts[i]
        a = rnd.uniform(0, 2 * math.pi) if k % 2 else la + rnd.uniform(-1.2, 1.2)
        L = P['spread'] * rnd.uniform(0.45, 0.9) * (1.15 - t * 0.6)
        end = base + Vector((math.cos(a) * L, math.sin(a) * L, rnd.uniform(-0.3, 0.6)))
        mid = base.lerp(end, 0.5) + Vector((rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), rnd.uniform(0.0, 0.5)))
        tr.tube(P['bark'], [base, mid, end], [rad[i] * 0.45, rad[i] * 0.3, 0.04], segs=6)
        _pad(nd, P['key'], end + Vector((0, 0, 0.25)), P['pad_size'] * rnd.uniform(0.7, 1.15) * (1.1 - t * 0.35), rnd)
    tr.finish()
    nd.finish()


@piece('cherry', height=6.0, spread=5.0, depth=4, blossoms=1.0, petals_ground=400, key='blossom', bark='bark_cherry')
def cherry(ctx, P, rnd):
    """Cherry tree (sakura): a short thick trunk splitting into recursive spreading branches, blossom clusters
    (faceted folded-paper puffs, translucent pink) at the tips, fallen petals on the ground under the crown."""
    tr = MB(ctx, ctx.info['name'] + '_wood', rnd)
    bl = MB(ctx, ctx.info['name'] + '_blossom', rnd)
    H = P['height']

    def branch(p, d, L, r, depth):
        n = 4
        pts = [p]
        for i in range(1, n + 1):
            q = pts[-1] + (d * (L / n)) + Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.5, 0.5))) * L * 0.06
            pts.append(q)
        tr.tube(P['bark'], pts, [r * (1 - 0.35 * i / n) for i in range(n + 1)], segs=7 if depth > 1 else 5)
        end = pts[-1]
        if depth == 0 or r < 0.025:
            if rnd.random() < P['blossoms'] + 0.2:
                for _ in range(rnd.randint(2, 4)):
                    c = end + Vector((rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), rnd.uniform(-0.2, 0.3)))
                    rr = rnd.uniform(0.32, 0.6) * (P['spread'] / 5)
                    res = bmesh.ops.create_icosphere(bl.bm, subdivisions=1, radius=1.0, matrix=M4(c, (0, 0, rnd.uniform(0, 90)), (rr, rr, rr * 0.75)))
                    for v in res['verts']:
                        v.co += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * rr * 0.18
                    bl.tag(bl.faces_of(res['verts']), P['key'])
            return
        kids = rnd.choice((2, 2, 3))
        for kk in range(kids):
            a = rnd.uniform(0, 2 * math.pi)
            spread = rnd.uniform(0.45, 0.9)
            nd = (d * (1 - spread) + Vector((math.cos(a), math.sin(a), 0.15)) * spread).normalized()
            nd.z = max(nd.z, -0.25)
            branch(end, nd.normalized(), L * rnd.uniform(0.62, 0.8), r * 0.62, depth - 1)
    branch(Vector((0, 0, -0.2)), Vector((0.08, 0.03, 1)).normalized(), H * 0.38, 0.28 * H / 6, P['depth'])
    tr.finish()
    bl.finish()
    if P['petals_ground'] > 0:
        pg = MB(ctx, ctx.info['name'] + '_fallen', rnd)
        for _ in range(P['petals_ground']):
            a = rnd.uniform(0, 2 * math.pi)
            rr = P['spread'] * 0.9 * math.sqrt(rnd.random())
            c = Vector((math.cos(a) * rr, math.sin(a) * rr, 0.004))
            s = rnd.uniform(0.018, 0.03)
            th = rnd.uniform(0, math.pi)
            u, v = Vector((math.cos(th), math.sin(th), 0)), Vector((-math.sin(th), math.cos(th), 0))
            pg.poly('petal', [c - u * s, c - v * s * 0.6 + Vector((0, 0, 0.003)), c + u * s, c + v * s * 0.6])
        pg.finish(shadow=False)


@piece('rocks', count=5, radius=3.0, size=[0.4, 1.4], key='stone_mossy', squash=0.6, sink=0.25, detail=2)
def rocks(ctx, P, rnd):
    """Weathered boulders scattered within `radius` (count 1 = one rock at the origin of `size[1]`): noise-
    displaced faceted forms, flattened and sunk into the ground, mossy tops."""
    mb = MB(ctx, ctx.info['name'], rnd)
    for i in range(P['count']):
        if P['count'] == 1:
            c, s = Vector((0, 0, 0)), P['size'][1]
        else:
            a = rnd.uniform(0, 2 * math.pi)
            rr = P['radius'] * math.sqrt(rnd.random())
            c = Vector((math.cos(a) * rr, math.sin(a) * rr, 0))
            if not ctx.is_clear((c.x, c.y), 0.3):
                continue
            s = rnd.uniform(*P['size'])
        m = M4(c + Vector((0, 0, s * P['squash'] * (0.5 - P['sink']))), (rnd.uniform(-8, 8), rnd.uniform(-8, 8), rnd.uniform(0, 360)),
               (s * rnd.uniform(0.8, 1.3) / 2, s * rnd.uniform(0.7, 1.0) / 2, s * P['squash'] / 2))
        res = bmesh.ops.create_icosphere(mb.bm, subdivisions=P['detail'], radius=1.0)
        sd = Vector((rnd.uniform(0, 99), rnd.uniform(0, 99), rnd.uniform(0, 99)))
        for v in res['verts']:
            p = v.co.copy()
            d = noise.noise(p * 1.3 + sd) * 0.28 + noise.noise(p * 3.1 + sd) * 0.1
            p = p * (1 + d)
            p.z = max(p.z, -0.7)
            v.co = m @ p
        mb.tag(mb.faces_of(res['verts']), P['key'])
    mb.finish()


@piece('treeline', width=60.0, depth=6.0, count=40, height=[8.0, 16.0], key='pine_needle', bark='bark')
def treeline(ctx, P, rnd):
    """Distant forest edge behind walls: cheap faceted conifer silhouettes (stacked cones) for skylines."""
    mb = MB(ctx, ctx.info['name'], rnd)
    for _ in range(P['count']):
        x, y = rnd.uniform(-P['width'] / 2, P['width'] / 2), rnd.uniform(-P['depth'] / 2, P['depth'] / 2)
        h = rnd.uniform(*P['height'])
        mb.cyl(P['bark'], 0.18, 0.1, h * 0.4, 5, loc=(x, y, h * 0.2))
        for k in range(4):
            t = 0.3 + 0.17 * k
            r = h * 0.28 * (1.1 - t)
            mb.cyl(P['key'], r, r * 0.15, h * 0.3, rnd.choice((6, 7)), loc=(x + rnd.uniform(-0.3, 0.3), y, h * t + h * 0.12), rot=(rnd.uniform(-4, 4), rnd.uniform(-4, 4), rnd.uniform(0, 60)))
    mb.finish()


# =========================================================================== atmosphere
@piece('fog', size=[60.0, 60.0, 20.0], density=0.02, color=[0.8, 0.84, 0.9], anisotropy=0.45, height=0.0, noise=0.0,
       noise_scale=0.12, absorption=0.0)
def fog(ctx, P, rnd):
    """Volumetric fog box (base on z = 0). `height` > 0 = ground mist thinning upward (density * exp(-z/height));
    `noise` 0..1 breaks it into drifting banks. Light shafts appear wherever a light is partly blocked."""
    sx, sy, sz = P['size']
    me = bpy.data.meshes.new(ctx.info['name'])
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=M4((0, 0, sz / 2), None, (sx, sy, sz)))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(ctx.info['name'], me)
    m = pm.new_material('SET_fog_' + ctx.info['name'])
    T = pm._NT(m.node_tree)
    out = m.node_tree.nodes.new('ShaderNodeOutputMaterial')
    dens = P['density']
    dsock = None
    if P['height'] > 0 or P['noise'] > 0:
        tc = T.node('ShaderNodeTexCoord')
        dsock = dens
        if P['height'] > 0:
            sep = T.node('ShaderNodeSeparateXYZ', Vector=tc.outputs['Object'])
            dsock = T.math('MULTIPLY', T.math('EXPONENT', T.math('DIVIDE', T.math('MULTIPLY', sep.outputs['Z'], -1.0), P['height'])), dens)
        if P['noise'] > 0:
            n = T.node('ShaderNodeTexNoise', Vector=tc.outputs['Object'], Scale=P['noise_scale'], Detail=3.0, Roughness=0.5)
            k = T.math('MULTIPLY_ADD', T.math('SUBTRACT', n.outputs['Fac'], 0.5), 2.5 * P['noise'], 1.0)
            k = T.math('MAXIMUM', k, 0.0)
            dsock = T.math('MULTIPLY', dsock, k)
    v = T.node('ShaderNodeVolumePrincipled')
    v.inputs['Color'].default_value = (*P['color'][:3], 1)
    v.inputs['Anisotropy'].default_value = P['anisotropy']
    v.inputs['Absorption Color'].default_value = (0, 0, 0, 1)
    if dsock is None:
        v.inputs['Density'].default_value = dens
    else:
        T.link(dsock, v.inputs['Density'])
    T.link(v.outputs[0], out.inputs['Volume'])
    me.materials.append(m)
    ob.visible_shadow = True
    ctx.link(ob)


def _cloud_mesh(ctx, name, pts, make):
    mb = MB(ctx, name, random.Random(name))
    for p in pts:
        make(mb, p)
    return mb


@piece('rain', area=[30.0, 30.0], height=14.0, count=6000, length=0.55, width=0.006, angle=8.0, speed=9.0)
def rain(ctx, P, rnd):
    """Rain: thin crossed streaks filling a box, looped falling animation (seamless, `speed` m/s). Pair it with
    wet materials (gravel_wet, wet=... on stone) and a backlight so the streaks catch the light."""
    W, D = P['area']
    H = P['height']
    tilt = math.radians(P['angle'])
    dvec = Vector((math.sin(tilt), 0, -math.cos(tilt)))
    mb = MB(ctx, ctx.info['name'], rnd)
    for rep in range(2):
        for _ in range(P['count'] // 2):
            c = Vector((rnd.uniform(-W / 2, W / 2), rnd.uniform(-D / 2, D / 2), rnd.uniform(0, H) + rep * H))
            ln = P['length'] * rnd.uniform(0.6, 1.3)
            a, b = c - dvec * ln / 2, c + dvec * ln / 2
            for side in (Vector((1, 0, 0)), Vector((0, 1, 0))):
                s = side * P['width']
                mb.poly('rain', [a - s, a + s, b + s, b - s], pr=0.5)
    ob = mb.finish(shadow=False)
    ob.visible_diffuse = False
    ob.keyframe_insert('location', index=2, frame=1)
    frames = H / P['speed'] * 24
    ob.location.z -= H
    ob.keyframe_insert('location', index=2, frame=1 + frames)
    ob.location.z += H
    try:
        fc = object_fcurves(ob)[0]
    except Exception:
        fc = None
        for layer in ob.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    fc = bag.fcurves[0]
    if fc:
        for k in fc.keyframe_points:
            k.interpolation = 'LINEAR'
        fc.modifiers.new('CYCLES')


def _particle_instance(ctx, kind, size):
    me = bpy.data.meshes.new('PI_' + kind)
    bm = bmesh.new()
    if kind == 'petals':
        vs = [bm.verts.new(v) for v in ((-1, 0, 0), (0, -0.55, 0.12), (1, 0, 0), (0, 0.6, 0.1))]
        bm.faces.new(vs)
    elif kind in ('embers', 'dust', 'snow', 'ash'):
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    else:
        bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('PI_' + kind + '_' + ctx.info['name'], me)
    key = {'petals': 'petal', 'embers': 'ember', 'dust': 'dust', 'snow': 'paper', 'ash': 'cloth_dark'}[kind]
    me.materials.append(ctx.mat(key))
    ob.location = (0, 0, -500)
    ob.hide_render = False
    ctx.link(ob, parent=False)
    return ob


@piece('particles', kind='petals', area=[16.0, 16.0, 6.0], count=500, size=0.03, velocity=[0.4, 0.1, -0.5],
       random=0.6, brownian=0.6, gravity=0.0, preroll=300)
def particles(ctx, P, rnd):
    """Drifting particles from a box (base on z = 0): kind 'petals' (cherry petals, tumbling), 'embers' (glowing,
    rising: give velocity z > 0), 'dust' (motes for light shafts), 'snow', 'ash'. Seeded and pre-rolled so frame 1
    is already full; animate by rendering later frames."""
    W, D, H = P['area']
    me = bpy.data.meshes.new(ctx.info['name'] + '_emitter')
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=M4((0, 0, H / 2), None, (W, D, H)))
    bm.to_mesh(me)
    bm.free()
    em = bpy.data.objects.new(ctx.info['name'] + '_emitter', me)
    ctx.link(em)
    em.show_instancer_for_render = False
    em.show_instancer_for_viewport = False
    inst = _particle_instance(ctx, P['kind'], P['size'])
    mod = em.modifiers.new('particles', 'PARTICLE_SYSTEM')
    ps = em.particle_systems[0]
    ps.seed = rnd.randint(0, 9999)
    s = ps.settings
    pre = int(P['preroll'])
    s.count = int(P['count'])
    s.frame_start = 1 - pre
    s.frame_end = 240
    s.lifetime = pre + 120
    s.lifetime_random = 0.4
    s.emit_from = 'VOLUME'
    s.distribution = 'RAND'
    s.use_emit_random = True
    s.physics_type = 'NEWTON'
    s.normal_factor = 0.0
    s.object_align_factor = tuple(v / 24.0 * 24.0 for v in P['velocity'])
    s.factor_random = P['random']
    s.brownian_factor = P['brownian']
    s.drag_factor = 0.2
    s.effector_weights.gravity = P['gravity']
    s.render_type = 'OBJECT'
    s.instance_object = inst
    s.particle_size = P['size']
    s.size_random = 0.5
    s.use_rotations = True
    s.rotation_mode = 'NONE'
    s.rotation_factor_random = 1.0
    s.angular_velocity_mode = 'RAND'
    s.angular_velocity_factor = 4.0 if P['kind'] == 'petals' else 0.0
    s.use_die_on_collision = False
    ps.point_cache.frame_start = 1 - pre
    ps.point_cache.frame_end = 240
    mod.show_render = True


@piece('light', type='POINT', energy=50.0, color=[1.0, 0.6, 0.3], size=0.1, look=None, spot=40.0, blend=0.3)
def light(ctx, P, rnd):
    """A practical or shaping light at the piece position: POINT, SPOT (with `spot` cone degrees; in fog = a
    visible beam / god ray), AREA (`size` m or [w, h]) or SUN. `look` = local target point."""
    ctx.light(P['type'], (0, 0, 0), P['energy'], P['color'], size=P['size'], look=P['look'], spot=P['spot'],
              blend=P['blend'], name=ctx.info['name'])


@piece('moon', elev=32.0, az=150.0, size=2.4, distance=900.0, color=[0.85, 0.9, 1.0], strength=6.0, halo=True)
def moon(ctx, P, rnd):
    """A cut-paper moon disc far away (visible only to the camera) with a soft halo card behind it."""
    el, az = math.radians(P['elev']), math.radians(P['az'])
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    r = P['distance'] * math.radians(P['size']) / 2
    for nm, rr, mat in (('disc', r, pm.paper_material('SET_moon_disc', P['color'], translucency=0.0, fibre_scale=0.08, facet_var=0.05,
                                                     glow=(P['color'], P['strength']))),
                        ('halo', r * 4.0, None)):
        if nm == 'halo' and not P['halo']:
            continue
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=True, segments=24 if nm == 'halo' else 15, radius=rr)
        me = bpy.data.meshes.new('MOON_' + nm)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new('MOON_' + nm, me)
        if mat is None:
            mat = pm.new_material('SET_moon_halo')
            T = pm._NT(mat.node_tree)
            out = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
            tc = T.node('ShaderNodeTexCoord')
            ln = T.node('ShaderNodeVectorMath', Vector=tc.outputs['Object']); ln.operation = 'LENGTH'
            f = T.math('POWER', T.math('SUBTRACT', 1.0, T.math('DIVIDE', ln.outputs['Value'], rr), clamp=True), 2.5)
            em = T.node('ShaderNodeEmission', Color=(*P['color'][:3], 1), Strength=T.math('MULTIPLY', f, P['strength'] * 0.06))
            tr = T.node('ShaderNodeBsdfTransparent')
            ad = T.node('ShaderNodeAddShader')
            T.link(em.outputs['Emission'], ad.inputs[0]); T.link(tr.outputs['BSDF'], ad.inputs[1])
            T.link(ad.outputs['Shader'], out.inputs['Surface'])
        me.materials.append(mat)
        ob.location = d * (P['distance'] + (5 if nm == 'halo' else 0))
        ob.rotation_euler = (-d).to_track_quat('Z', 'Y').to_euler()
        for attr in ('visible_shadow', 'visible_diffuse', 'visible_glossy', 'visible_transmission', 'visible_volume_scatter'):
            setattr(ob, attr, False)
        ctx.link(ob, parent=False)


# =========================================================================== 2.5D layered backgrounds
def _ridge(rnd, n_pow=6, start=6, rough=0.55):
    h = [rnd.uniform(0.2, 1.0) for _ in range(start)]
    amp = 0.5
    for _ in range(n_pow):
        nh = []
        for i in range(len(h) - 1):
            a, b = h[i], h[i + 1]
            nh += [a, (a + b) / 2 + rnd.uniform(-amp, amp)]
        nh.append(h[-1])
        h = nh
        amp *= rough
    lo, hi = min(h), max(h)
    return [(v - lo) / (hi - lo + 1e-9) for v in h]


def _sil_mountains(rnd, W, H, smooth=False):
    hs = _ridge(rnd, 6 if not smooth else 4, 7, 0.55 if not smooth else 0.4)
    n = len(hs)
    pts = [(-W / 2 + W * i / (n - 1), H * (0.25 + 0.75 * h)) for i, h in enumerate(hs)]
    return [[(-W / 2, -3)] + pts + [(W / 2, -3)]], []


def _sil_trees(rnd, W, H):
    polys = [[(-W / 2, -3), (W / 2, -3), (W / 2, H * 0.3), (-W / 2, H * 0.3)]]
    x = -W / 2
    while x < W / 2:
        h = H * rnd.uniform(0.55, 1.0)
        w = h * rnd.uniform(0.22, 0.35)
        if rnd.random() < 0.7:            # conifer: stacked jagged tiers
            tiers = rnd.randint(3, 5)
            for t in range(tiers):
                z0 = H * 0.25 + (h - H * 0.25) * t / tiers
                ww = w * (1 - t / (tiers + 0.6))
                polys.append([(x - ww, z0), (x + ww, z0), (x + ww * 0.15, z0 + (h - H * 0.25) / tiers * 1.6), (x - ww * 0.1, z0 + (h - H * 0.25) / tiers * 1.7)])
        else:                              # broadleaf: faceted crown
            k = 9
            polys.append([(x + w * 1.2 * math.cos(2 * math.pi * j / k) * rnd.uniform(0.75, 1.1), h * 0.72 + h * 0.3 * math.sin(2 * math.pi * j / k) * rnd.uniform(0.75, 1.1)) for j in range(k)])
            polys.append([(x - w * 0.08, -1), (x + w * 0.08, -1), (x + w * 0.05, h * 0.6), (x - w * 0.05, h * 0.6)])
        x += w * rnd.uniform(0.9, 1.6)
    return polys, []


def _sil_clouds(rnd, W, H):
    polys = []
    for _ in range(int(W / (H * 3)) + 2):
        cx, cz = rnd.uniform(-W / 2, W / 2), rnd.uniform(0, H)
        L = H * rnd.uniform(2.5, 5)
        for _b in range(rnd.randint(3, 6)):
            bx = cx + rnd.uniform(-L / 2, L / 2)
            r = H * rnd.uniform(0.18, 0.4)
            k = 8
            polys.append([(bx + r * 1.6 * math.cos(2 * math.pi * j / k), cz + r * 0.6 * max(-0.2, math.sin(2 * math.pi * j / k))) for j in range(k)])
    return polys, []


def _sil_castle(rnd, W, H, storeys=4, x0=0.0, walls=True):
    """Castle skyline cut-out: battered base, stacked storeys with flared roofs and gables, lit windows,
    turrets and a long wall with a gate tower."""
    polys, wins = [], []
    bw = H * 0.62
    bh = H * 0.22
    polys.append([(x0 - bw / 2 - bh * 0.25, -3), (x0 + bw / 2 + bh * 0.25, -3), (x0 + bw / 2, bh), (x0 - bw / 2, bh)])
    z = bh
    w = bw * 0.85
    sh = (H - bh) / (storeys + 0.6)
    for i in range(storeys):
        polys.append([(x0 - w / 2, z - 0.1), (x0 + w / 2, z - 0.1), (x0 + w / 2, z + sh * 0.62), (x0 - w / 2, z + sh * 0.62)])
        for k in range(max(1, int(w / (sh * 0.55)))):
            nwin = max(1, int(w / (sh * 0.55)))
            wx = x0 - w / 2 + w * (k + 0.5) / nwin
            if rnd.random() < 0.6:
                wins.append((wx, z + sh * 0.18, sh * 0.16, sh * 0.2))
        rz = z + sh * 0.6
        ow = w / 2 + sh * 0.55
        top = i == storeys - 1
        rh = sh * (0.75 if top else 0.42)
        tip = sh * 0.18
        polys.append([(x0 - ow - tip, rz + tip), (x0 - ow, rz), (x0 + ow, rz), (x0 + ow + tip, rz + tip),
                      (x0 + w * (0.18 if top else 0.42), rz + rh), (x0 - w * (0.18 if top else 0.42), rz + rh)])
        if 0 < i < storeys - 1:
            gw = w * 0.35
            polys.append([(x0 - gw / 2, rz + rh * 0.4), (x0 + gw / 2, rz + rh * 0.4), (x0, rz + rh * 0.4 + gw * 0.5)])
        if top:
            for sx in (-1, 1):
                polys.append([(x0 + sx * w * 0.18, rz + rh), (x0 + sx * (w * 0.18 + sh * 0.12), rz + rh + sh * 0.25), (x0 + sx * w * 0.12, rz + rh)])
        z = rz + rh * 0.85
        w *= 0.8
    if walls:
        wh = H * 0.13
        polys.append([(-W / 2, -3), (W / 2, -3), (W / 2, wh), (-W / 2, wh)])
        for tx in (x0 - bw * 1.4, x0 + bw * 1.5, x0 - bw * 2.6):
            tw = H * rnd.uniform(0.14, 0.2)
            th = wh + H * rnd.uniform(0.12, 0.18)
            polys.append([(tx - tw / 2, wh - 0.5), (tx + tw / 2, wh - 0.5), (tx + tw / 2, th), (tx - tw / 2, th)])
            polys.append([(tx - tw / 2 - tw * 0.3, th - tw * 0.05), (tx + tw / 2 + tw * 0.3, th - tw * 0.05), (tx + tw * 0.15, th + tw * 0.4), (tx - tw * 0.15, th + tw * 0.4)])
            if rnd.random() < 0.7:
                wins.append((tx, th - tw * 0.5, tw * 0.18, tw * 0.22))
    return polys, wins


SILHOUETTES = {'mountains': _sil_mountains, 'hills': lambda r, W, H: _sil_mountains(r, W, H, True), 'trees': _sil_trees,
               'clouds': _sil_clouds, 'castle': _sil_castle}


def _card_material(name, color, haze_color, haze, glow, translucency, image=None):
    col = tuple(c * (1 - haze) + h * haze for c, h in zip(color, haze_color))
    em = tuple(h * haze * glow for h in haze_color)
    m = pm.paper_material(name, col, translucency=translucency, fibre_scale=0.6, fibre_strength=0.25, facet_var=0.0,
                          rough=0.9, glow=(em, 1.0) if glow > 0 and haze > 0 else None, translucent_color=(1.0, 0.65, 0.4))
    if image:
        img = bpy.data.images.load(os.path.abspath(image), check_existing=True)
        nt = m.node_tree
        out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
        surf = out.inputs['Surface'].links[0].from_socket
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nt.links.new(tc.outputs['UV'], tex.inputs['Vector'])
        tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        mx = nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(tex.outputs['Alpha'], mx.inputs[0])
        nt.links.new(tr.outputs['BSDF'], mx.inputs[1])
        nt.links.new(surf, mx.inputs[2])
        nt.links.new(mx.outputs['Shader'], out.inputs['Surface'])
        for n in nt.nodes:                  # the image colour replaces the flat card colour
            if n.type == 'BSDF_PRINCIPLED':
                mul = nt.nodes.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MIX'
                mul.inputs[0].default_value = haze
                nt.links.new(tex.outputs['Color'], mul.inputs[6])
                mul.inputs[7].default_value = (*haze_color, 1)
                nt.links.new(mul.outputs[2], n.inputs['Base Color'])
    return m


@piece('layers', layers=[
    {'shape': 'trees', 'dist': 40, 'height': 14, 'color': [0.04, 0.045, 0.04], 'haze': 0.15},
    {'shape': 'castle', 'dist': 90, 'height': 45, 'color': [0.05, 0.05, 0.06], 'haze': 0.3},
    {'shape': 'hills', 'dist': 180, 'height': 40, 'color': [0.06, 0.06, 0.08], 'haze': 0.5},
    {'shape': 'mountains', 'dist': 400, 'height': 110, 'color': [0.08, 0.08, 0.1], 'haze': 0.7},
    {'shape': 'clouds', 'dist': 600, 'height': 60, 'z': 120, 'color': [0.5, 0.45, 0.45], 'haze': 0.6}],
    haze_color=[0.55, 0.42, 0.38], glow=0.6, translucency=0.35, thickness=0.004, window_glow=[1.0, 0.55, 0.2, 12.0],
    fov_width=1.3)
def layers(ctx, P, rnd):
    """2.5D paper-cut backdrop: flat silhouette cards (shape 'mountains', 'hills', 'trees', 'clouds', 'castle', or
    'image' with `image` = PNG with alpha) standing upright at increasing `dist` along +Y, each card's colour pulled
    toward `haze_color` by its `haze` (0 near .. 1 far) and lit a little from inside (`glow`), so a moving camera
    gets real parallax and depth with almost no render cost. Per layer: shape, dist, width (default dist *
    fov_width + 30), height, z (base), x, color, haze, seed, storeys (castle), windows (castle lit windows)."""
    hz = P['haze_color']
    for li, L in enumerate(P['layers']):
        r = random.Random(f"{ctx.seed}:{ctx.info['name']}:{li}:{L.get('seed', 0)}")
        dist = L['dist']
        W = L.get('width', dist * P['fov_width'] * 2 + 30)
        H = L.get('height', 20)
        nm = f"{ctx.info['name']}_{li}_{L.get('shape', 'card')}"
        mat = _card_material('SET_' + nm, L.get('color', [0.1, 0.1, 0.1]), hz, L.get('haze', 0.3), P['glow'],
                             L.get('translucency', P['translucency']), L.get('image'))
        me = bpy.data.meshes.new(nm)
        bm = bmesh.new()
        x0, z0 = L.get('x', 0.0), L.get('z', 0.0)
        if L.get('shape') == 'image':
            img = bpy.data.images.load(os.path.abspath(L['image']), check_existing=True)
            iw, ih = img.size
            Wd = H * iw / max(1, ih)
            vs = [bm.verts.new((x0 + a * Wd / 2, dist, z0 + b)) for a, b in ((-1, 0), (1, 0), (1, H), (-1, H))]
            f = bm.faces.new(vs)
            uv = bm.loops.layers.uv.new('UVMap')
            for loop, co in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                loop[uv].uv = co
            wins = []
        else:
            kw = {'storeys': L['storeys']} if L.get('shape') == 'castle' and 'storeys' in L else {}
            polys, wins = SILHOUETTES[L.get('shape', 'mountains')](r, W, H, **kw)
            for poly in polys:
                vs = [bm.verts.new((x0 + x, dist, z0 + z)) for x, z in poly]
                try:
                    bm.faces.new(vs[::-1])
                except ValueError:
                    pass
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(nm, me)
        me.materials.append(mat)
        if L.get('windows', True) and wins:
            wc = P['window_glow']
            wm = pm.emission_material('SET_' + nm + '_win', wc[:3], wc[3])
            me.materials.append(wm)
            bm = bmesh.new()
            bm.from_mesh(me)
            for (wx, wz, ww, wh) in wins:
                vs = [bm.verts.new((x0 + wx + a * ww / 2, dist - 0.05 - li * 0.0, z0 + wz + b * wh)) for a, b in ((1, 0), (-1, 0), (-1, 1), (1, 1))]
                f = bm.faces.new(vs)
                f.material_index = 1
            bm.to_mesh(me)
            bm.free()
        if P['thickness'] > 0 and L.get('shape') != 'image':
            sm = ob.modifiers.new('card', 'SOLIDIFY')
            sm.thickness = P['thickness'] * dist
        ob.visible_shadow = L.get('shadow', False)
        ctx.link(ob)


# =========================================================================== Ganryujima (port of blender/world)
def _bw(ctx, P):
    """Import blender/world/build_world.py as a library, pointed at this set's scene and collection."""
    import importlib
    import collections as _c
    bw = sys.modules.get('build_world') or importlib.import_module('build_world')
    bw.scene = ctx.scene
    bw.COLL = _c.defaultdict(lambda: ctx.coll)
    bw.SEED = P.get('seed', 1)
    bw.SUN_ELEV = ctx.info.get('sun_elev', 4.0)
    bw.SUN_AZ = ctx.info.get('sun_az', -7.0)
    bw.ISL_PH = [bw.rng('shore').uniform(0, 6.28) for _ in range(4)]
    pm.SKY.update(sun_elevation=math.radians(bw.SUN_ELEV), sun_rotation=math.radians(bw.SUN_AZ), dust_density=1.3)
    return bw


@piece('boat', length=5.2, beam=1.25, depth=0.5, sheer=0.35, key='wood_aged', trim='wood_dark', thwarts=3, oar=True)
def boat(ctx, P, rnd):
    """A small wooden rowing boat (kobune) along +X, bow at +X: a flat bottom, two flared side planks folded up
    from it, a sheer that rises to a pointed bow, a flat transom, gunwale strips, thwarts and the stern oar (ro).
    The boat that brings Musashi to the island (research/ganryujima.md: tradition) - nothing in the kit was one.
    Waterline z = 0 at the origin; built from flat planes, so it reads as folded card like the rest of the set."""
    mb = MB(ctx, ctx.info['name'], rnd)
    L, B, D = P['length'], P['beam'], P['depth']
    n = 10
    rows = []
    for i in range(n + 1):
        t = i / n                                      # 0 = stern, 1 = bow
        x = -L / 2 + L * t
        nose = max(0.0, (t - 0.72) / 0.28)             # the last quarter narrows to the stem
        half_top = B / 2 * (0.86 + 0.14 * math.sin(math.pi * min(t, 0.8) / 0.8)) * (1 - nose ** 1.4) + 0.015
        half_bot = half_top * 0.62 * (1 - nose)
        z_bot = -D * 0.55 + nose * D * 0.45            # the bottom sweeps up into the bow
        z_top = D * 0.45 + P['sheer'] * nose ** 2 + 0.05 * (1 - t)
        rows.append(((x, -half_bot, z_bot), (x, half_bot, z_bot), (x, -half_top, z_top), (x, half_top, z_top)))
    for a, b in zip(rows, rows[1:]):
        mb.poly(P['key'], [a[0], b[0], b[1], a[1]])              # bottom
        mb.poly(P['key'], [a[0], a[2], b[2], b[0]])              # port side
        mb.poly(P['key'], [a[1], b[1], b[3], a[3]])              # starboard side
    s = rows[0]
    mb.poly(P['key'], [s[0], s[1], s[3], s[2]])                  # transom
    for side in (2, 3):                                          # gunwale strips along both top edges
        for a, b in zip(rows, rows[1:]):
            beam_between(mb, P['trim'], a[side], b[side], 0.05, 0.05)
    for k in range(P['thwarts']):
        r = rows[int((0.25 + 0.5 * k / max(1, P['thwarts'] - 1)) * n)]
        mb.box(P['trim'], (0.18, abs(r[3][1] - r[2][1]) * 0.96, 0.04), loc=(r[2][0], 0, r[2][2] - 0.12))
    if P['oar']:                                                 # the ro: a long sweep over the stern into the sea
        st = Vector(s[2]).lerp(Vector(s[3]), 0.5) + Vector((0.15, 0, 0.1))
        tip = st + Vector((-2.6, 0.4, -0.9))
        beam_between(mb, P['key'], st + Vector((0.6, -0.1, 0.35)), tip, 0.05, 0.05)
        mb.box(P['key'], (0.6, 0.02, 0.16), loc=tip + Vector((0.25, -0.04, 0.09)), rot=(0, -19, 9))
    mb.finish()


def _kit_pines(ctx, bw):
    """The beach's pines as kit `pine` pieces - a leaning, kinked trunk with crooked BRANCHES ending in flat cloud
    pads of needles - on the spots build_world.build_pines uses. That one stacks cones on a five-sided stick, so
    every tree read as a plastic Christmas tree with no branch at all (Mark, Nov 26: "the tree, the branch").
    Same spots and the same seeded lean toward the sea, so cameras and marks keep their sight lines."""
    r = bw.rng('pines')
    spots = [(-22, 11), (-15, 15), (-8, 13.5), (-2, 16), (5, 12.5), (11, 16), (17, 13), (24, 10), (-27, 6)]
    keep = ctx.root, ctx.info
    for idx, (px, py) in enumerate(spots):
        px += r.uniform(-1.5, 1.5)
        py += r.uniform(-1, 1)
        h = r.uniform(6.5, 11.0)
        build_piece(ctx, {'kit': 'pine', 'name': f'PINE_{idx}', 'seed': idx,
                          'pos': (px, py, bw.island_height(px, py) - 0.3),
                          'params': {'height': h, 'spread': h * 0.55, 'lean': r.uniform(10, 24),
                                     'lean_dir': -90 + r.uniform(-25, 25), 'pads': r.randint(5, 8)}})
    ctx.root, ctx.info = keep


@piece('ganryujima', seed=1, sea=True, island=True, rocks=True, pines=True, mountains=True, clouds=True, paper_sun=True,
       realistic=True, foam=0.05)
def ganryujima(ctx, P, rnd):
    """The Ganryujima island world (blender/world/build_world.py) as one kit piece: Ocean-modifier paper sea,
    faceted island with the duel beach on -Y, rocks, kuromatsu pines, cut-paper mountain rings, paper clouds and
    the paper sun. `realistic` swaps sand, rocks and bark for the textured set materials. World coordinates."""
    ctx.info.update(ctx.scene.get('set_sun', {}))
    bw = _bw(ctx, P)
    # level the sand under the fighter marks (ctx.clear: the set's MARK_hero / MARK_foe / MARK_center zones)
    bw.FLAT[:] = [(x, y, r) for x, y, r in getattr(ctx, 'fight', [])] if P.get('flatten', True) else []
    bw._FLAT_Z.clear()
    before = set(bpy.data.objects)
    if P['paper_sun']:
        d = bw.sun_dir() * 3200.0
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=True, segments=14, radius=3200.0 * math.radians(2.2))
        mat = pm.paper_material('LO_PaperSun', (1.0, 0.55, 0.25), translucency=0.0, facet_var=0.04, fibre_scale=0.05,
                                glow=((1.0, 0.45, 0.15), 160.0))
        ob = bw.obj_from_bm('SKY_paper_sun', bm, mat, 'SKY', 3)
        ob.location = d
        ob.rotation_euler = (-bw.sun_dir()).to_track_quat('Z', 'Y').to_euler()
        ob.visible_shadow = False
        ob.visible_diffuse = False
    for part, fn in (('sea', bw.build_sea), ('island', bw.build_island), ('rocks', bw.build_rocks), ('pines', bw.build_pines),
                     ('mountains', bw.build_mountains), ('clouds', bw.build_clouds)):
        if part == 'pines' and P['pines'] == 'kit':
            _kit_pines(ctx, bw)
        elif P[part]:
            fn()
    if P['realistic']:
        # `foam` = the share of sea cells allowed a white cap. 0.05 scattered torn white patches over open water that
        # read as floating paper rubbish in every low shot; the shoreline lace (build_island) is separate and stays.
        calm = pm.sea_material('LO_SeaPaperCalm', haze=(None, 1400.0, 1.0), foam_cells=float(P['foam']), foam_gain=2.5,
                               crest_gain=1.5)
        swap = {'LO_PaperSand': ctx.mat('sand'), 'LO_PaperRock': ctx.mat('stone_mossy'), 'LO_PaperBark': ctx.mat('bark'),
                'LO_SeaPaper': calm}
        for ob in set(bpy.data.objects) - before:
            if ob.type == 'MESH':
                for i, m in enumerate(ob.data.materials):
                    if m and m.name in swap:
                        ob.data.materials[i] = swap[m.name]


# =========================================================================== the village pieces
# minka, machiya, well, bamboo_fence, stall, nobori, chochin, ph_prop live in blender/sets/kit_village.py and
# register into this same KIT (as `kit`, also when this file runs as a script)
sys.modules.setdefault('kit', sys.modules[__name__])
import kit_village  # noqa: E402,F401
# pagoda, shrine_hall, shrine, hill: blender/sets/kit_temple.py (same registration)
import kit_temple  # noqa: E402,F401

# =========================================================================== CLI: list the kit
if __name__ == '__main__':
    print(describe())
