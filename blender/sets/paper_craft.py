"""PAPER CRAFT: the set option `"paper": "craft"` (Mark, 28 Nov: the palace "with the texture", the look of his
paper-craft boards). The kit's procedural stone, plaster, tile and wood read as a realistic 3D place; this pass
turns a built set into a PAPER MODEL of itself:

  - every kit material (`SET_*`) becomes a SHEET of paper of its colour: washi plaster, dark card roofs, kraft
    stones with near-black backfill between them, brown card wood, red card lacquer, green card pines... each
    facet its own tone (facet_rand), washi fibres. Glows (lit windows, lantern paper, shoji) stay as they are.
  - every building mesh gets fold lines (paper_materials.add_fold_lines, folds sharper than `angle`) and the
    characters' paper surface (paper_surface: ink in the valleys, a light edge on the ridges, a mottle, soft
    occlusion), with the ink line `width` metres wide: 3-6 cm at architecture distance (a character's 3.5 mm line
    is sub-pixel on a keep 50 m away).
  - the sea, sky, paper sun, mountains, clouds, 2.5D cards, fog and particles are left alone (their look is theirs).

Called by blender/sets/build_set.py when a set's JSON says `"paper": "craft"` (or
`"paper": {"look": "craft", "width": 0.03, "angle": 35}`) and by blender/sets/palace/paperize_set.py on an already
built .blend. Only objects in the SET collection are touched when it exists, so characters keep their own paper.
"""
import bpy

import paper_materials as pm

DEFAULTS = {'look': 'craft', 'width': 0.03, 'angle': 35.0, 'ink': 0.85, 'light': 0.45, 'mottle': 0.14,
            'mottle_scale': 0.8, 'ao': 0.4, 'sheets': True, 'colors': {}}
# "colors": {"earth": [0.2, 0.3, 0.1]} recolours a sheet for this set (checked before SHEETS, same substring rule)

# objects / materials whose look is their own
# (prefixes only: a substring test once skipped the palace's 'sea_gate' along with the sea)
SKIP_NAMES = ('SEA', 'SKY', 'LO_Mount', 'MOUNT', 'CLOUD', 'LAYER', 'FOG', 'PI_', 'MOON')
SKIP_KITS = ('fog', 'particles', 'rain', 'moon', 'layers', 'light')      # ob['pc_kit'], written by build_set.py
SKIP_MATS = ('LO_Sea', 'LO_PaperSun', 'LO_Mount', 'LO_Cloud', 'SET_rain', 'SET_ember', 'SET_dust', 'SET_petal')

# (material key contains, colour (linear RGB) or None = keep, facet_var, fibre_scale); FIRST match wins, so the
# specific keys come before the general ones ('wood_dark' before 'wood', 'stone_dressed' before 'stone')
SHEETS = [
    ('window_glow', None, 0, 0), ('lantern_paper', None, 0, 0), ('shoji', None, 0, 0), ('glow', None, 0, 0),
    ('plaster_earth', (0.42, 0.30, 0.19), 0.07, 6.0), ('plaster', (0.80, 0.74, 0.62), 0.07, 6.0),
    ('tile', (0.105, 0.11, 0.125), 0.10, 8.0), ('copper', (0.16, 0.36, 0.30), 0.10, 8.0),
    ('gold', (0.62, 0.42, 0.13), 0.08, 10.0), ('window_dark', (0.035, 0.03, 0.03), 0.05, 8.0),
    ('wood_dark', (0.12, 0.075, 0.05), 0.08, 8.0), ('wood_aged', (0.28, 0.19, 0.12), 0.08, 8.0),
    ('wood_light', (0.52, 0.37, 0.22), 0.08, 8.0), ('wood_floor', (0.36, 0.22, 0.12), 0.08, 8.0),
    ('wood_post', (0.18, 0.11, 0.065), 0.08, 8.0), ('wood', (0.30, 0.19, 0.11), 0.08, 8.0),
    ('cypress_edge', (0.50, 0.33, 0.19), 0.08, 8.0), ('cypress', (0.22, 0.12, 0.07), 0.10, 8.0),
    ('shide', (0.92, 0.90, 0.84), 0.04, 10.0),
    ('lacquer_red', (0.50, 0.07, 0.04), 0.06, 8.0), ('lacquer_black', (0.03, 0.028, 0.026), 0.05, 8.0),
    ('stone_dressed', (0.46, 0.44, 0.40), 0.12, 5.0), ('stone_mossy', (0.27, 0.30, 0.22), 0.12, 5.0),
    ('stone_dark', (0.17, 0.16, 0.15), 0.10, 5.0), ('stone_lantern', (0.42, 0.40, 0.37), 0.10, 6.0),
    # the stones light, the gaps between them near-black: a cut-paper wall reads by its dark gaps (with both in tan
    # paper the stone pattern vanished, 28 Nov)
    ('stone', (0.50, 0.48, 0.44), 0.16, 5.0), ('backfill', (0.045, 0.04, 0.035), 0.05, 5.0),
    ('gravel', (0.40, 0.39, 0.36), 0.12, 4.0), ('sand', (0.55, 0.46, 0.33), 0.10, 4.0),
    ('forest_floor', (0.14, 0.12, 0.07), 0.12, 4.0), ('moss', (0.12, 0.20, 0.07), 0.12, 6.0),
    ('earth', (0.33, 0.25, 0.17), 0.10, 4.0),
    ('thatch_dark', (0.20, 0.15, 0.08), 0.10, 8.0), ('thatch', (0.42, 0.32, 0.17), 0.10, 8.0),
    ('iron', (0.07, 0.07, 0.075), 0.06, 8.0), ('pine_needle', (0.05, 0.10, 0.06), 0.10, 10.0),
    ('bamboo_leaf', (0.10, 0.17, 0.05), 0.10, 10.0), ('bamboo', (0.30, 0.34, 0.12), 0.10, 8.0),
    ('bark', (0.13, 0.085, 0.06), 0.10, 8.0), ('rope', (0.55, 0.45, 0.28), 0.08, 10.0),
    ('banner_white', (0.85, 0.82, 0.74), 0.06, 10.0), ('cloth_white', (0.85, 0.82, 0.74), 0.06, 10.0)]


def config(value):
    """The set's "paper" value -> settings dict, or None when the look is off ("paper": "craft" | {...} | false)."""
    if not value:
        return None
    if isinstance(value, str):
        value = {'look': value}
    c = dict(DEFAULTS)
    c.update(value)
    return c if c.get('look') == 'craft' else None


class _Sheets:
    def __init__(self, colors=None):
        self.made = {}
        self.table = [(k, tuple(v), 0.10, 6.0) for k, v in (colors or {}).items()] + SHEETS

    def __call__(self, m):
        if not m or not m.name.startswith('SET_'):
            return m
        key = m.name[4:]
        for k, col, fv, fs in self.table:
            if k in key:
                if col is None:
                    return m                        # a glow stays as it is
                if key not in self.made:
                    self.made[key] = pm.paper_material('PC_sheet_' + key, col, translucency=0.0, fibre_scale=fs,
                                                       fibre_strength=0.10, facet_var=fv, flat=True, seed=len(self.made))
                return self.made[key]
        return m


def _volume_only(m):
    if not m.use_nodes:
        return False
    out = next((n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    return bool(out and not out.inputs['Surface'].is_linked and out.inputs['Volume'].is_linked)


def _targets(scene):
    coll = bpy.data.collections.get('SET')
    obs = coll.all_objects if coll is not None else scene.objects
    for ob in obs:
        if ob.type != 'MESH' or not len(ob.data.polygons):
            continue
        if ob.name.startswith(SKIP_NAMES) or ob.get('pc_kit') in SKIP_KITS:
            continue
        if any(m and _volume_only(m) for m in ob.data.materials):
            continue
        if any(m and m.name.startswith(SKIP_MATS) for m in ob.data.materials):
            continue
        if ob.get('pc_no_paper'):
            continue
        yield ob


def apply(scene, cfg=None, log=print):
    """Paper-craft every set mesh of `scene` in place. Returns {'meshes', 'folds', 'materials', 'surfaced'}."""
    c = config(cfg if cfg is not None else 'craft')
    if c is None:
        return None
    sheet = _Sheets(c['colors']) if c['sheets'] else (lambda m: m)
    folds, done, mats = 0, 0, []
    for ob in _targets(scene):
        if ob.data.get('pc_folded'):              # shared mesh data (instances), or a second pass: fold it once
            mats += [m for m in ob.data.materials if m and m not in mats]
            continue
        for i, m in enumerate(ob.data.materials):
            ob.data.materials[i] = sheet(m)
        pm.add_facet_attribute(ob, seed=done)
        folds += pm.add_fold_lines(ob, c['angle'])
        ob.data['pc_folded'] = 1
        done += 1
        mats += [m for m in ob.data.materials if m and m not in mats]
    up = sum(1 for m in mats if pm.paper_surface(m, ink=c['ink'], width=c['width'], light=c['light'], mottle=c['mottle'],
                                                 mottle_scale=c['mottle_scale'], ao=c['ao']))
    scene['paper_look'] = 'craft'
    log('[paper craft] %d meshes, %d folds sharper than %.0f deg, paper surface on %d of %d materials (ink line %.0f cm)'
        % (done, folds, c['angle'], up, len(mats), c['width'] * 100))
    return {'meshes': done, 'folds': folds, 'materials': len(mats), 'surfaced': up}
