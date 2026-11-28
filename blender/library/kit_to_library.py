"""KIT -> LIBRARY: the set kit's pieces (blender/sets/kit.py + kit_village.py, used as they are) as library assets:
each piece built alone with the kit's own builder, its procedural materials turned into flat sheets of paper of their
colour (the colour table of blender/sets/palace/paperize_set.py --craft, else the recipe's own colour), glows kept as
glowing sheets, then the same output as tools/paperize_model.py: paper.glb, preview.png, paper.json, plus the built
original.blend (procedural materials) as the 'original'.

  $B -b -P blender/library/kit_to_library.py -- --out output/library/kit [--only minka,well]

The list of pieces and their params: KIT_ASSETS below (id -> kit piece, params, kind, tags).
"""
import inspect
import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
for d in ('blender/sets', 'blender/world', 'blender', 'blender/library'):
    p = os.path.join(REPO, d)
    if p not in sys.path:
        sys.path.insert(0, p)
import kit as K  # noqa: E402
import kit_village  # noqa: E402,F401  (registers the village pieces)
import paperlook as PL  # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = ARGV[ARGV.index('--out') + 1] if '--out' in ARGV else os.path.join(REPO, 'output', 'library', 'kit')
ONLY = ARGV[ARGV.index('--only') + 1].split(',') if '--only' in ARGV else None

KIT_ASSETS = {   # library id kit/<key>: (kit piece, params, kind, tags)
    'minka': ('minka', {}, 'building', ['village', 'farm']),
    'minka_small': ('minka', {'width': 7.0, 'depth': 5.5}, 'building', ['village', 'farm', 'forest']),
    'machiya': ('machiya', {}, 'building', ['village', 'market']),
    'machiya_narrow': ('machiya', {'width': 4.5, 'lit': 0.3}, 'building', ['village', 'market']),
    'well': ('well', {}, 'building', ['village']),
    'stall': ('stall', {}, 'building', ['village', 'market']),
    'bamboo_fence': ('bamboo_fence', {}, 'building', ['village', 'forest']),
    'bamboo_fence_open': ('bamboo_fence', {'style': 'yotsume'}, 'building', ['village', 'farm', 'riverside']),
    'nobori': ('nobori', {}, 'prop', ['village', 'market']),
    'chochin': ('chochin', {}, 'prop', ['village', 'market', 'light']),
    'torii': ('torii', {}, 'building', ['village', 'forest', 'shrine']),
    'toro': ('toro', {}, 'building', ['village', 'shrine', 'riverside', 'light']),
    'bridge': ('bridge', {}, 'building', ['riverside', 'village']),
    'plaster_wall': ('plaster_wall', {'length': 8.0}, 'building', ['village', 'castle']),
    'boat': ('boat', {}, 'prop', ['riverside']),
    'pine': ('pine', {}, 'tree', ['forest', 'village', 'riverside']),
    'cherry': ('cherry', {'petals_ground': 0}, 'tree', ['village', 'riverside', 'shrine']),
    'rocks': ('rocks', {'count': 4, 'radius': 1.5}, 'rock', ['forest', 'riverside', 'village']),
}

SHEETS = [   # (material key contains, linear colour): blender/sets/palace/paperize_set.py's --craft table, extended
    ('plaster_earth', (0.42, 0.31, 0.20)), ('plaster', (0.80, 0.74, 0.62)), ('tile', (0.105, 0.11, 0.125)),
    ('gold', (0.62, 0.42, 0.13)), ('window_dark', (0.035, 0.03, 0.03)), ('wood_dark', (0.12, 0.075, 0.05)),
    ('wood_aged', (0.28, 0.19, 0.12)), ('wood_light', (0.55, 0.40, 0.25)), ('wood_post', (0.20, 0.12, 0.07)),
    ('wood_floor', (0.36, 0.22, 0.12)), ('wood', (0.24, 0.15, 0.09)), ('lacquer_red', (0.50, 0.07, 0.04)),
    ('lacquer_black', (0.03, 0.028, 0.026)), ('stone_dressed', (0.46, 0.44, 0.40)), ('stone_mossy', (0.27, 0.30, 0.22)),
    ('stone_dark', (0.17, 0.16, 0.15)), ('stone_lantern', (0.42, 0.40, 0.37)), ('stone', (0.50, 0.48, 0.44)),
    ('backfill', (0.045, 0.04, 0.035)), ('earth', (0.33, 0.25, 0.17)), ('iron', (0.07, 0.07, 0.075)),
    ('pine_needle', (0.05, 0.10, 0.06)), ('bark_cherry', (0.11, 0.07, 0.06)), ('bark', (0.13, 0.085, 0.06)),
    ('thatch_dark', (0.12, 0.09, 0.05)), ('thatch_edge', (0.42, 0.33, 0.18)), ('thatch', (0.32, 0.24, 0.12)),
    ('bamboo_leaf', (0.09, 0.14, 0.035)), ('bamboo', (0.30, 0.36, 0.10)), ('shoji', (0.90, 0.87, 0.78)),
]
GLOWS = {'window_glow': ((0.95, 0.80, 0.55), ((1.0, 0.55, 0.22), 6.0)),
         'lantern_paper': ((0.95, 0.85, 0.65), ((1.0, 0.55, 0.2), 1.5))}


def sheet_colour(key):
    """(linear colour, glow or None) for a kit material key."""
    base = key.split('#')[0]
    if base in GLOWS:
        return GLOWS[base]
    for k, col in SHEETS:
        if k in base:
            return col, None
    recipes = K._M()
    if base in recipes:
        fn, kw = recipes[base]
        if 'color' in kw:
            return tuple(kw['color'])[:3], None
        try:
            c = inspect.signature(fn).parameters['color'].default
            if c is not inspect.Parameter.empty:
                return tuple(c)[:3], None
        except (KeyError, ValueError):
            pass
    return (0.6, 0.58, 0.54), None


def build_one(key, piece, params):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    ctx = K.Ctx(sc, seed=1)
    K.build_piece(ctx, {'kit': piece, 'name': key, 'params': params})
    bpy.context.view_layer.update()
    os.makedirs(os.path.join(OUT, key), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, key, 'original.blend'), compress=True)
    dg = bpy.context.evaluated_depsgraph_get()
    tmp = []
    for o in list(sc.objects):
        if o.type in ('MESH', 'CURVE') and not o.hide_render:
            me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
            t = bpy.data.objects.new('tmp_' + o.name, me)
            t.matrix_world = o.matrix_world.copy()
            sc.collection.objects.link(t)
            tmp.append(t)
    for o in list(sc.objects):
        if o not in tmp:
            bpy.data.objects.remove(o, do_unlink=True)
    ob = PL.join_meshes(tmp, 'PAPER_' + key)
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)
    me = ob.data
    n_in = len(me.polygons)
    # one sheet per kit material
    new, sheets = [], []
    for i, m in enumerate(me.materials):
        mk = m.name[4:] if m and m.name.startswith('SET_') else (m.name if m else 'paper')
        col, glow = sheet_colour(mk)
        new.append(PL._sheet_material('PC_sheet_%s_%s' % (key, mk), col, glow=glow))
        sheets.append({'name': new[-1].name, 'srgb': [round(float(v), 3) for v in PL.lin_to_srgb(col)], 'cut': False,
                       'glow': bool(glow), 'from': mk})
    for i, m in enumerate(new):
        me.materials[i] = m
    PL.flat_shade(ob)
    off, size = PL.settle([ob])
    st = {'id': 'kit/' + key, 'piece': piece, 'params': params, 'faces_in': n_in, 'faces': len(me.polygons),
          'tris': sum(len(p.vertices) - 2 for p in me.polygons), 'size_m': [round(v, 4) for v in size],
          'offset_m': [round(v, 4) for v in off], 'sheets': sheets, 'flat': True, 'materials': len(me.materials)}
    ob['pc_asset'] = 'kit/' + key
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    glb = os.path.join(OUT, key, 'paper.glb')
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_extras=True,
                              export_apply=True, export_materials='EXPORT')
    st['glb_mb'] = round(os.path.getsize(glb) / 1e6, 3)
    st['folds'] = PL.paper_look(ob, size=max(size))
    PL.studio(ob, os.path.join(OUT, key, 'preview.png'), res=(512, 512), samples=32, az=-30, el=18)
    json.dump(st, open(os.path.join(OUT, key, 'paper.json'), 'w'), indent=1)
    print('[kit] %s (%s): %d faces, %d sheets, size %s m, glb %.2f MB' % (key, piece, st['faces'], len(sheets),
                                                                      st['size_m'], st['glb_mb']), flush=True)


for key, (piece, params, kind, tags) in KIT_ASSETS.items():
    if ONLY and key not in ONLY:
        continue
    try:
        build_one(key, piece, params)
    except Exception as e:  # one broken piece must not stop the rest
        import traceback
        traceback.print_exc()
        print('[kit] %s FAILED: %s' % (key, e), flush=True)
