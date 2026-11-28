"""TEMPLE KIT: a hill shrine and its pagoda (Mark, 28 Nov: "create building").

    pagoda        five-storey pagoda (gojunoto): a dressed-stone platform, storeys stepping in, red-lacquer posts and
                  white plaster bays, a ring of bracket blocks under every deep eave, a balcony rail on the upper
                  storeys, tiled pent roofs with upturned corners, a square top roof and the bronze spire (sorin:
                  base, bowl, nine rings, water flame, jewel)
    shrine_hall   Shinto main hall (honden, nagare-zukuri): raised on round red posts, a plank floor with a veranda
                  and rail, lattice doors, plaster side walls, a thick curved cypress-bark roof whose front slope runs
                  long over the wooden steps (on two posts), gable boards, a green copper ridge with crossed chigi and
                  katsuogi logs, a straw rope with paper streamers across the front
    shrine        the whole shrine as ONE piece: the hall, a red torii, a stone path from the torii to the steps and
                  pairs of stone lanterns along it (`lanterns` pairs), a purification basin (chozuya) optional
    hill          a mound: a flat terrace on top (radius `top`, height `height`), slopes falling smoothly to the ground
                  at `base`, noise bumps on the slopes, an optional straight cut for a stair down the front (-Y)

Registered into kit.KIT (kit.py imports this module at its end, after kit_village): local metres, Z up, the front
faces -Y, built from the same MB builder and material keys (new keys: cypress, cypress_edge, copper, rope, shide).
Every piece wears the paper craft look when the set says "paper": "craft" (blender/sets/paper_craft.py).
"""
import math

import kit as K
from kit import M4, MB, beam_between, hip_roof, piece

if K.HAVE_BPY:
    import bmesh
    import bpy
    from mathutils import Vector, noise
    import paper_materials as pm

# --------------------------------------------------------------------------- materials
_prev_M = getattr(K, '_M', None)


def _temple_M():
    d = _prev_M()
    d.update({
        # hiwadabuki: layered cypress bark shingles, grain down the slope; the cut eave edge shows the light layers
        'cypress': (pm.wood_material, dict(color=(0.16, 0.085, 0.05), color2=(0.08, 0.04, 0.025), axis='Y', grain=1.6,
                                           rough=0.9, wear=0.0, ph='wood')),
        'cypress_edge': (pm.wood_material, dict(color=(0.42, 0.27, 0.15), color2=(0.30, 0.18, 0.09), axis='X', grain=2.5,
                                                rough=0.85, wear=0.0)),
        'copper': (pm.paper_material, dict(color=(0.13, 0.32, 0.26), translucency=0.0, rough=0.55, fibre_scale=30, facet_var=0.08)),
        'rope': (pm.wood_material, dict(color=(0.55, 0.45, 0.26), color2=(0.38, 0.30, 0.16), axis='X', grain=3.0,
                                        rough=0.95, wear=0.0)),
        'shide': (pm.paper_material, dict(color=(0.92, 0.90, 0.84), translucency=0.4, fibre_scale=60)),
    })
    return d


if K.HAVE_BPY:
    K._M = _temple_M


# =========================================================================== pagoda
def _bracket_ring(mb, w, z, rnd, key='wood_aged', tip='plaster', step=0.85, tiers=2):
    """Bracket blocks (kumimono) under an eave: `tiers` rows of blocks stepping out from the wall top all round,
    each block with a white end (the painted rafter-end look)."""
    for t in range(tiers):
        out = 0.22 + 0.32 * t
        zz = z - 0.42 + 0.26 * t
        for side in range(4):
            n = max(2, int(round(w / step)))
            for i in range(n + 1):
                u = -w / 2 + w * i / n
                if side == 0:
                    loc, sz = (u, -w / 2 - out / 2, zz), (0.22, out + 0.1, 0.2)
                elif side == 1:
                    loc, sz = (w / 2 + out / 2, u, zz), (out + 0.1, 0.22, 0.2)
                elif side == 2:
                    loc, sz = (u, w / 2 + out / 2, zz), (0.22, out + 0.1, 0.2)
                else:
                    loc, sz = (-w / 2 - out / 2, u, zz), (out + 0.1, 0.22, 0.2)
                mb.box(key, sz, loc=loc, pr=rnd.random())
        # a beam ring on the tier (the bearing block row)
        for side in range(4):
            if side % 2 == 0:
                mb.box(key, (w + 2 * out, 0.16, 0.12), loc=(0, (-1 if side == 0 else 1) * (w / 2 + out), zz + 0.16))
            else:
                mb.box(key, (0.16, w + 2 * out, 0.12), loc=((1 if side == 1 else -1) * (w / 2 + out), 0, zz + 0.16))
    # white rafter ends just under the eave line
    o = 0.22 + 0.32 * tiers + 0.12
    for side in range(4):
        n = max(4, int(round(w / 0.45)))
        for i in range(n + 1):
            u = -w / 2 - o + (w + 2 * o) * i / n
            loc = [(u, -w / 2 - o, z - 0.22), (w / 2 + o, u, z - 0.22), (u, w / 2 + o, z - 0.22), (-w / 2 - o, u, z - 0.22)][side]
            mb.box(tip, (0.1, 0.1, 0.1), loc=loc)


def _bays(mb, rnd, w, z0, z1, *, post='lacquer_red', wall='plaster', door='wood_dark', bays=3, doors=True):
    """One square storey w x w: plaster core, red posts at the corners and bay lines, red head and sill beams, a
    plank door in the middle bay of every face (or a dark window on the upper storeys)."""
    h = z1 - z0
    mb.box(wall, (w, w, h), loc=(0, 0, (z0 + z1) / 2), pr=rnd.random())
    for side in range(4):
        ax = side % 2
        sign = -1 if side in (0, 3) else 1
        for i in range(bays + 1):
            u = -w / 2 + w * i / bays
            loc = (u, sign * w / 2, (z0 + z1) / 2) if ax == 0 else (sign * w / 2, u, (z0 + z1) / 2)
            mb.box(post, (0.2, 0.2, h), loc=loc)
        for zb, hb in ((z1 - 0.14, 0.2), (z0 + 0.1, 0.16)):
            mb.box(post, (w + 0.24, 0.16, hb) if ax == 0 else (0.16, w + 0.24, hb),
                   loc=(0, sign * (w / 2 + 0.02), zb) if ax == 0 else (sign * (w / 2 + 0.02), 0, zb))
        bw = w / bays
        dh = h * (0.68 if doors else 0.36)
        dz = z0 + 0.2 + dh / 2 if doors else z0 + h * 0.5
        key = door if doors else 'window_dark'
        size = (bw * 0.7, 0.06, dh) if ax == 0 else (0.06, bw * 0.7, dh)
        loc = (0, sign * (w / 2 + 0.03), dz) if ax == 0 else (sign * (w / 2 + 0.03), 0, dz)
        mb.box(key, size, loc=loc, pr=rnd.random())
        if doors:                                   # gilt fittings: two rows of studs on the door
            for zz in (dz - dh * 0.3, dz + dh * 0.3):
                for k in (-1, 1):
                    q = (k * bw * 0.18, sign * (w / 2 + 0.07), zz) if ax == 0 else (sign * (w / 2 + 0.07), k * bw * 0.18, zz)
                    mb.box('gold', (0.08, 0.04, 0.08) if ax == 0 else (0.04, 0.08, 0.08), loc=q)


def _rail_ring(mb, w, z, key='lacquer_red', floor='wood_aged'):
    """A balcony round a storey: plank floor ring, posts, top and middle rails."""
    o = 0.55
    W = w + 2 * o
    for side in range(4):
        ax = side % 2
        sign = -1 if side in (0, 3) else 1
        c = sign * (w / 2 + o / 2)
        mb.box(floor, (W, o, 0.08) if ax == 0 else (o, W, 0.08), loc=(0, c, z) if ax == 0 else (c, 0, z))
        e = sign * (w / 2 + o - 0.05)
        for hz, hh in ((0.62, 0.07), (0.32, 0.05)):
            mb.box(key, (W, 0.07, hh) if ax == 0 else (0.07, W, hh), loc=(0, e, z + hz) if ax == 0 else (e, 0, z + hz))
        n = max(2, int(round(W / 0.9)))
        for i in range(n + 1):
            u = -W / 2 + W * i / n
            mb.box(key, (0.08, 0.08, 0.66), loc=(u, e, z + 0.33) if ax == 0 else (e, u, z + 0.33))


def _sorin(mb, z, H, rnd, pole='iron', rings='gold'):
    """The spire (sorin) from the roof apex at z: square base, inverted bowl, lotus, a pole with nine rings, a
    water flame of four crossed blades, the dragon-jewel and the top jewel. H = its height."""
    k = H / 8.0
    mb.box(pole, (1.0 * k, 1.0 * k, 0.45 * k), loc=(0, 0, z + 0.1 * k), bevel=0.03)
    mb.cyl(pole, 0.5 * k, 0.32 * k, 0.45 * k, 12, loc=(0, 0, z + 0.55 * k))          # fukubachi
    mb.cyl(rings, 0.28 * k, 0.48 * k, 0.3 * k, 12, loc=(0, 0, z + 0.92 * k))          # ukebana
    mb.cyl(pole, 0.08 * k, 0.07 * k, H - 1.0 * k, 8, loc=(0, 0, z + 1.0 * k + (H - 1.0 * k) / 2))
    for i in range(9):
        r = (0.46 - 0.018 * i) * k
        mb.cyl(rings, r, r * 0.92, 0.09 * k, 12, loc=(0, 0, z + (1.25 + 0.5 * i) * k))
    zf = z + 6.0 * k
    for a in range(4):                                                                 # suien: 4 flame blades
        ang = math.pi / 4 * a
        c, s = math.cos(ang), math.sin(ang)
        pts = [(-0.42 * k, 0, 0), (-0.12 * k, 0, 0.75 * k), (0, 0, 1.0 * k), (0.12 * k, 0, 0.75 * k), (0.42 * k, 0, 0)]
        mb.poly(rings, [(px * c, px * s, zf + pz) for px, _, pz in pts], pr=0.3)
        mb.poly(rings, [(px * c, px * s, zf + pz) for px, _, pz in pts[::-1]], pr=0.3)
    for zz, r in ((zf + 1.25 * k, 0.17 * k), (zf + 1.62 * k, 0.13 * k)):
        res = bmesh.ops.create_icosphere(mb.bm, subdivisions=1, radius=r, matrix=M4((0, 0, zz), None, (1, 1, 1.2)))
        mb.tag(mb.faces_of(res['verts']), rings)


@piece('pagoda', base_w=6.2, storeys=5, storey_h=2.9, taper=0.32, overhang=1.9, pitch=24.0, upturn=0.55,
       platform=1.1, spire=8.0, post='lacquer_red', wall='plaster', roof='tile', stone='stone_dressed', brackets=True)
def pagoda(ctx, P, rnd):
    """Five-storey pagoda (gojunoto): stone platform with front steps, square storeys stepping in by `taper` a side,
    red posts, plaster bays, doors on the ground storey, bracket blocks under the deep eaves, balconies on the upper
    storeys, tiled pent roofs with upturned corners, a square top roof and the bronze spire. Front faces -Y."""
    st = MB(ctx, ctx.info['name'] + '_stone', rnd)
    walls = MB(ctx, ctx.info['name'] + '_walls', rnd)
    roofs = MB(ctx, ctx.info['name'] + '_roofs', rnd)
    w0, ph = P['base_w'], P['platform']
    pw = w0 + 2 * P['overhang'] + 0.6
    st.box(P['stone'], (pw, pw, ph), loc=(0, 0, ph / 2), bevel=0.04)
    st.box(P['stone'], (pw + 0.3, pw + 0.3, 0.22), loc=(0, 0, 0.11), bevel=0.03)          # plinth course
    n_st = max(1, int(round(ph / 0.22)))
    for i in range(n_st):                                                               # front steps
        st.box(P['stone'], (2.2, 0.36, ph * (i + 1) / n_st), loc=(0, -pw / 2 - 0.36 * (n_st - i) + 0.18, ph * (i + 1) / n_st / 2), bevel=0.02)
    st.finish()
    z = ph
    o = P['overhang']
    sori = 1.35
    n = P['storeys']
    for i in range(n):
        top = i == n - 1
        wi = w0 - 2 * P['taper'] * i
        sh = P['storey_h'] * (0.92 if i else 1.0)
        zb = z - (0.0 if i == 0 else 0.5)
        zt = z + sh
        _bays(walls, rnd, wi, zb, zt, post=P['post'], wall=P['wall'], doors=(i == 0))
        if i > 0:
            _rail_ring(walls, wi, z + 0.05, key=P['post'])
        if P['brackets']:
            _bracket_ring(walls, wi, zt, rnd)
        ze = zt + 0.25
        oi = o * (1.0 - 0.06 * i)
        if top:
            rise = hip_roof(roofs, wi, wi, pitch=P['pitch'] + 6, overhang=oi, upturn=P['upturn'], z0=ze, ridge=False,
                            soffit='wood_aged')
            roofs.box(P['roof'], (0.9, 0.9, 0.35), loc=(0, 0, ze + rise + 0.05))
            _sorin(roofs, ze + rise + 0.2, P['spire'], rnd)
            break
        wn = wi - 2 * P['taper']
        Do = wi / 2 + oi
        vmax = (Do - wn / 2 - 0.55) / Do                     # stop at the balcony of the storey above
        rise = hip_roof(roofs, wi, wi, pitch=P['pitch'], overhang=oi, upturn=P['upturn'], z0=ze, v_max=vmax, ridge=False,
                        soffit='wood_aged')
        z = ze + rise * vmax ** sori + 0.05
    walls.finish()
    roofs.finish()


# =========================================================================== shrine hall (nagare-zukuri)
def _curved_roof(mb, W, y_back, y_ridge, y_front, z_ridge, z_back, z_front, *, thick=0.32, sori=1.7, upturn=0.25,
                 key='cypress', edge='cypress_edge', under='wood_aged', nu=24):
    """A thick two-slope roof along X (width W): the ridge at y_ridge / z_ridge, the back eave at y_back / z_back and
    the front eave at y_front / z_front; each slope concave (steep at the ridge, flattening to the eave: `sori`),
    the eave corners lifted by `upturn`. Top, underside and the cut edge all round."""
    def slope(y0, z0):
        def f(u, v):                                  # u along X, v from the ridge (0) to the eave (1)
            x = -W / 2 + W * u
            y = y_ridge + (y0 - y_ridge) * v
            zz = z0 + (z_ridge - z0) * (1 - v) ** sori + upturn * abs(2 * u - 1) ** 3 * v ** 2
            return Vector((x, y, zz))
        return f
    for y0, z0, front in ((y_front, z_front, True), (y_back, z_back, False)):
        f = slope(y0, z0)
        nv = max(8, int(abs(y0 - y_ridge) / 0.5))
        dn = Vector((0, 0, thick))
        # faces must point up: on the front slope (v toward -Y) u has to run -X, on the back slope +X
        if front:
            mb.grid(key, lambda u, v: f(1 - u, v), nu, nv, lambda i, j: ((i * 13 + j * 7) % 31) / 31.0)
            mb.grid(under, lambda u, v: f(u, v) - dn, nu, nv)
        else:
            mb.grid(key, lambda u, v: f(u, v), nu, nv, lambda i, j: ((i * 11 + j * 5) % 29) / 29.0)
            mb.grid(under, lambda u, v: f(1 - u, v) - dn, nu, nv)
        # the cut edge: the eave line and both gable verges
        for i in range(nu):
            a, b = f(i / nu, 1.0), f((i + 1) / nu, 1.0)
            mb.poly(edge, [a - dn, b - dn, b, a] if front else [b - dn, a - dn, a, b])
        for side in (0.0, 1.0):
            for j in range(nv):
                a, b = f(side, j / nv), f(side, (j + 1) / nv)
                pts = [a, b, b - dn, a - dn]
                mb.poly(edge, pts if (side == 0.0) == front else pts[::-1])


@piece('shrine_hall', width=7.2, depth=5.6, floor_h=1.3, wall_h=3.0, front_ext=2.8, pitch=30.0, overhang=1.0,
       roof='cypress', post='lacquer_red', wall='plaster', chigi=True, katsuogi=3, rope=True, steps=True)
def shrine_hall(ctx, P, rnd):
    """Shinto main hall (honden, nagare-zukuri) on round red posts: raised plank floor with a veranda and rail on
    three sides, wooden steps up the front under the long front slope of a thick curved cypress-bark roof (on two
    front posts), lattice doors, plaster side and back walls, gable boards, green copper ridge with crossed chigi
    finials and katsuogi logs, a straw rope with paper streamers. Front faces -Y."""
    st = MB(ctx, ctx.info['name'] + '_base', rnd)
    fr = MB(ctx, ctx.info['name'] + '_frame', rnd)
    rf = MB(ctx, ctx.info['name'] + '_roof', rnd)
    W, D, Fh, Wh = P['width'], P['depth'], P['floor_h'], P['wall_h']
    post = P['post']
    # stone base (kidan)
    st.box('stone_dressed', (W + 2.6, D + 2.6, 0.38), loc=(0, 0.2, 0.19), bevel=0.04)
    # floor posts on foundation stones, the floor, the veranda
    nx, ny = 4, 3
    for i in range(nx + 1):
        for j in range(ny + 1):
            x, y = -W / 2 + W * i / nx, -D / 2 + D * j / ny
            st.stone('stone_dressed', (0.42, 0.42, 0.18), M4((x, y, 0.42)), rnd, square=0.4, bulge=0.0, chip=0.04, flat_back=False)
            edge = i in (0, nx) or j in (0, ny)
            top = Fh + Wh if edge else Fh
            fr.cyl(post, 0.15, 0.15, top - 0.42, 12, loc=(x, y, 0.42 + (top - 0.42) / 2))
    fr.box('wood_aged', (W + 0.3, D + 0.3, 0.16), loc=(0, 0, Fh - 0.08))                          # floor
    v = 0.95                                                                                      # veranda width
    for (sx, sy, lx, ly) in ((0, -1, W + 2 * v, v), (-1, 0, v, D + v), (1, 0, v, D + v)):
        cx = sx * (W / 2 + v / 2)
        cy = sy * (D / 2 + v / 2) if sy else -v / 2
        fr.box('wood_aged', (lx, ly, 0.1), loc=(cx, cy, Fh - 0.12))
    # veranda rail (left, right and the front either side of the steps)
    rz = Fh + 0.62
    for x0, y0, x1, y1 in ((-W / 2 - v + 0.05, -D / 2 - v + 0.05, -1.0, -D / 2 - v + 0.05),
                           (1.0, -D / 2 - v + 0.05, W / 2 + v - 0.05, -D / 2 - v + 0.05),
                           (-W / 2 - v + 0.05, -D / 2 - v + 0.05, -W / 2 - v + 0.05, D / 2),
                           (W / 2 + v - 0.05, -D / 2 - v + 0.05, W / 2 + v - 0.05, D / 2)):
        a, b = Vector((x0, y0, rz)), Vector((x1, y1, rz))
        beam_between(fr, post, a, b, 0.09, 0.08)
        beam_between(fr, post, a - Vector((0, 0, 0.3)), b - Vector((0, 0, 0.3)), 0.06, 0.05)
        L = (b - a).length
        for k in range(int(L / 0.9) + 1):
            p = a.lerp(b, k / max(1, int(L / 0.9)))
            fr.box(post, (0.09, 0.09, 0.66), loc=(p.x, p.y, Fh + 0.3))
    # walls: front = lattice doors (shitomi) in the bays, sides and back = plaster in red frames
    z0, z1 = Fh, Fh + Wh
    fr.box(post, (W + 0.36, 0.2, 0.24), loc=(0, -D / 2, z1 - 0.1))
    fr.box(post, (W + 0.36, 0.2, 0.2), loc=(0, D / 2, z1 - 0.1))
    for sx in (-1, 1):
        fr.box(post, (0.2, D + 0.36, 0.22), loc=(sx * W / 2, 0, z1 - 0.1))
    for i in range(nx):
        x0, x1 = -W / 2 + W * i / nx + 0.16, -W / 2 + W * (i + 1) / nx - 0.16
        cx, bw = (x0 + x1) / 2, x1 - x0
        fr.box('wood_dark', (bw, 0.08, Wh - 0.3), loc=(cx, -D / 2 + 0.02, z0 + (Wh - 0.3) / 2), pr=rnd.random())
        for r in range(1, 8):                                       # the lattice (black bars over the dark panel)
            zz = z0 + (Wh - 0.3) * r / 8
            fr.box('lacquer_black', (bw, 0.04, 0.035), loc=(cx, -D / 2 - 0.04, zz))
        for c in range(1, 5):
            fr.box('lacquer_black', (0.035, 0.04, Wh - 0.3), loc=(x0 + bw * c / 5, -D / 2 - 0.04, z0 + (Wh - 0.3) / 2))
        fr.box(P['wall'], (bw, 0.1, Wh - 0.3), loc=(cx, D / 2 - 0.02, z0 + (Wh - 0.3) / 2), pr=rnd.random())
    for j in range(ny):
        y0, y1 = -D / 2 + D * j / ny + 0.16, -D / 2 + D * (j + 1) / ny - 0.16
        for sx in (-1, 1):
            fr.box(P['wall'], (0.1, y1 - y0, Wh - 0.3), loc=(sx * (W / 2 - 0.02), (y0 + y1) / 2, z0 + (Wh - 0.3) / 2), pr=rnd.random())
    # roof: ridge over the back third, a long front slope over the steps
    o = P['overhang']
    t = math.tan(math.radians(P['pitch']))
    y_ridge = D * 0.1
    y_back = D / 2 + o
    z_wall = z1 + 0.12
    z_ridge = z_wall + (y_back - y_ridge) * t * 0.95 + 0.25
    z_back = z_wall - 0.25
    y_front = -D / 2 - o - P['front_ext']
    z_front = z_wall - 0.25 - P['front_ext'] * 0.3
    Wr = W + 2 * o
    _curved_roof(rf, Wr, y_back, y_ridge, y_front, z_ridge, z_back, z_front, key=P['roof'])
    # gable boards filling the triangle between the wall top and the roof on both ends
    for sx in (-1, 1):
        x = sx * (W / 2 + 0.05)
        pts = [(x, -D / 2, z_wall - 0.1), (x, D / 2, z_wall - 0.1), (x, y_ridge, z_ridge - 0.35)]
        fr.poly('wood_aged', pts if sx > 0 else pts[::-1])
        for a, b in (((x, -D / 2 - 0.3, z_wall), (x, y_ridge, z_ridge - 0.25)), ((x, D / 2 + 0.3, z_wall), (x, y_ridge, z_ridge - 0.25))):
            beam_between(fr, 'wood_light', Vector(a), Vector(b), 0.08, 0.14)
    # ridge: green copper cap, katsuogi logs across it, chigi (crossed forked boards) at both gable ends
    rf.box('copper', (Wr + 0.1, 0.5, 0.36), loc=(0, y_ridge, z_ridge + 0.1), bevel=0.04)
    rf.box('copper', (Wr - 0.2, 0.3, 0.14), loc=(0, y_ridge, z_ridge + 0.34))
    kn = int(P['katsuogi'])
    for k in range(kn):
        x = -W * 0.32 + (W * 0.64) * (k / max(1, kn - 1) if kn > 1 else 0.5)
        rf.cyl('wood_light', 0.16, 0.16, 0.95, 10, loc=(x, y_ridge, z_ridge + 0.6), rot=(90, 0, 0))
        for e in (-1, 1):
            rf.cyl('gold', 0.17, 0.17, 0.06, 10, loc=(x, y_ridge + e * 0.48, z_ridge + 0.6), rot=(90, 0, 0))
    if P['chigi']:
        for sx in (-1, 1):
            x = sx * (Wr / 2 - 0.2)
            for sy in (-1, 1):
                a = Vector((x, y_ridge + sy * 0.6, z_ridge - 0.3))
                b = Vector((x, y_ridge - sy * 0.9, z_ridge + 1.6))
                beam_between(rf, 'cypress_edge', a, b, 0.08, 0.3)
    # front: the two posts holding the long eave (kohai), the steps, the rope
    yp = y_front + 0.9
    vp = (yp - y_ridge) / (y_front - y_ridge)
    zt = z_front + (z_ridge - z_front) * (1 - vp) ** 1.7 - 0.32 - 0.02          # just under the roof's underside
    for sx in (-1, 1):
        x = sx * (W / 2 - 0.9)
        st.stone('stone_dressed', (0.4, 0.4, 0.2), M4((x, yp, 0.45)), rnd, square=0.4, bulge=0.0, chip=0.04, flat_back=False)
        fr.box(post, (0.2, 0.2, zt - 0.45), loc=(x, yp, 0.45 + (zt - 0.45) / 2))
        fr.box(post, (0.24, abs(-D / 2 - yp) + 0.2, 0.22), loc=(x, (yp - D / 2) / 2, zt - 0.05))
    fr.box(post, (W - 1.4, 0.2, 0.24), loc=(0, yp, zt - 0.17))
    if P['steps']:
        n = max(3, int(round((Fh - 0.38) / 0.2)))
        run = 0.3
        for k in range(n):
            zk = 0.38 + (Fh - 0.38) * (k + 1) / n
            yk = -D / 2 - v - run * (n - k) + run / 2
            fr.box('wood_aged', (2.0, run + 0.02, 0.07), loc=(0, yk, zk - 0.035))
        for sx in (-1, 1):
            beam_between(fr, 'wood_aged', Vector((sx * 1.05, -D / 2 - v - run * n, 0.42)), Vector((sx * 1.05, -D / 2 - v, Fh)), 0.1, 0.26)
    if P['rope']:
        y = -D / 2 - v - 0.15
        pts, radii = [], []
        for k in range(13):
            u = k / 12
            x = -W / 2 - 0.2 + (W + 0.4) * u
            pts.append((x, y, z1 - 0.15 - 0.35 * math.sin(math.pi * u)))
            radii.append(0.06 + 0.07 * math.sin(math.pi * u))
        fr.tube('rope', pts, radii, segs=8)
        for k in (2, 4, 6, 8, 10):                      # shide: zigzag paper streamers
            px, py, pz = pts[k]
            zz = pz - radii[k]
            zig = [(0, 0), (0.12, -0.12), (0.0, -0.24), (0.12, -0.36), (0.0, -0.48), (0.12, -0.6)]
            for m in range(len(zig) - 1):
                (a0, b0), (a1, b1) = zig[m], zig[m + 1]
                q = [(px + a0 - 0.06, py - 0.01, zz + b0), (px + a0 + 0.06, py - 0.01, zz + b0),
                     (px + a1 + 0.06, py - 0.01, zz + b1), (px + a1 - 0.06, py - 0.01, zz + b1)]
                fr.poly('shide', q[::-1])
    st.finish()
    fr.finish()
    rf.finish()


# =========================================================================== the whole shrine
def _sub(ctx, kind, name, pos, rot, params, rnd):
    """Build kit piece `kind` as a child of the current piece, at `pos` / `rot` in its frame."""
    parent = ctx.root
    sub = bpy.data.objects.new('SET_' + name, None)
    sub.empty_display_size = 0.3
    sub.location = Vector(pos)
    sub.rotation_euler = (0, 0, math.radians(rot))
    sub.parent = parent
    sub['kit'] = kind
    ctx.coll.objects.link(sub)
    bpy.context.view_layer.update()
    k = K.KIT[kind]
    P = dict(k['defaults'])
    P.update(params or {})
    info = ctx.info
    ctx.root, ctx.info = sub, {'name': name, 'kind': kind}
    k['fn'](ctx, P, rnd)
    ctx.root, ctx.info = parent, info
    return sub


@piece('shrine', path=14.0, path_w=2.4, lanterns=3, torii_h=5.4, torii_span=4.2, hall={}, torii={}, toro={}, chozuya=True)
def shrine(ctx, P, rnd):
    """A whole Shinto shrine in one piece: the main hall (shrine_hall, params in `hall`) at the back, a red torii
    (`torii`) at the front, a stone path (`path` m) between them with `lanterns` pairs of stone lanterns (`toro`),
    and a purification basin under a little roof beside the path. The origin is the torii's centre; the path runs
    +Y to the hall's steps. Front faces -Y."""
    nm = ctx.info['name']
    hp = dict(K.KIT['shrine_hall']['defaults'])
    hp.update(P['hall'])
    y_hall = P['path'] + hp['depth'] / 2 + 0.95 + 0.3 * max(3, int(round((hp['floor_h'] - 0.38) / 0.2))) + 0.6
    _sub(ctx, 'torii', nm + '_torii', (0, 0, 0), 0, dict({'height': P['torii_h'], 'span': P['torii_span']}, **P['torii']), rnd)
    _sub(ctx, 'paving', nm + '_path', (0, (P['path'] + 1.5) / 2 - 0.75, 0), 0,
         {'length': P['path'] + 1.5, 'width': P['path_w'], 'along': 'Y'}, rnd)
    n = int(P['lanterns'])
    for i in range(n):
        y = 2.2 + (P['path'] - 3.4) * (i / max(1, n - 1) if n > 1 else 0.5)
        for sx in (-1, 1):
            _sub(ctx, 'toro', f'{nm}_toro_{i}{"lr"[sx > 0]}', (sx * (P['path_w'] / 2 + 1.1), y, 0), 0,
                 dict({'height': 1.9, 'energy': 10.0}, **P['toro']), rnd)
    _sub(ctx, 'shrine_hall', nm + '_hall', (0, y_hall, 0), 0, P['hall'], rnd)
    if P['chozuya']:
        mb = MB(ctx, nm + '_chozuya', rnd)
        x0, y0 = P['path_w'] / 2 + 3.2, 3.0
        mb.stone('stone_dressed', (1.5, 0.9, 0.7), M4((x0, y0, 0.35)), rnd, square=0.3, bulge=0.0, chip=0.04, flat_back=False)
        mb.box('window_dark', (1.2, 0.6, 0.04), loc=(x0, y0, 0.71))                # the water (dark)
        for sx in (-1, 1):
            for sy in (-1, 1):
                mb.box('lacquer_red', (0.14, 0.14, 2.3), loc=(x0 + sx * 0.95, y0 + sy * 0.7, 1.15))
        K.gable_roof(mb, 2.6, 2.0, pitch=30, overhang=0.35, z0=2.3, key='tile', offset=(x0, y0, 0))
        mb.finish()


# =========================================================================== hill
@piece('hill', top=14.0, base=34.0, height=6.0, key='forest_floor', res=96, bumps=0.35, bump_scale=0.12,
       cut_width=0.0, cut_depth=0.35)
def hill(ctx, P, rnd):
    """A mound: a flat terrace of radius `top` at `height`, slopes falling smoothly to z 0 at radius `base`, noise
    bumps on the slopes only (the terrace stays flat for marks). `cut_width` > 0 cuts a straight ramp down the front
    (-Y) for a stair: the ground there follows the straight line from the terrace edge to the foot, `cut_depth`
    lower. The mesh is a (2*base) square grid; outside `base` it is flat at 0."""
    mb = MB(ctx, ctx.info['name'], rnd)
    T, Bs, H = P['top'], P['base'], P['height']
    sd = Vector((rnd.uniform(0, 99), rnd.uniform(0, 99), 0))
    cw = P['cut_width']

    def prof(r):
        if r <= T:
            return H
        if r >= Bs:
            return 0.0
        t = (r - T) / (Bs - T)
        return H * (1 - (3 * t * t - 2 * t * t * t))

    def f(u, v):
        x, y = (u - 0.5) * 2 * Bs * 1.1, (v - 0.5) * 2 * Bs * 1.1
        r = math.hypot(x, y)
        z = prof(r)
        if T < r < Bs:
            w = math.sin(math.pi * (r - T) / (Bs - T))
            z += noise.noise(Vector((x, y, 0)) * P['bump_scale'] + sd) * P['bumps'] * w
        if cw > 0 and y < -T * 0.9:
            ramp = H * max(0.0, min(1.0, (y + Bs) / (Bs - T))) - P['cut_depth']
            d = abs(x) - cw / 2
            if d < 2.0:
                k = 1.0 if d <= 0 else 1 - (3 * (d / 2) ** 2 - 2 * (d / 2) ** 3)
                z = z + (min(z, ramp) - z) * k
        return (x, y, z)
    mb.grid(P['key'], f, P['res'], P['res'])
    mb.finish(smooth=True)
