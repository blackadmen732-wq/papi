"""AI MANIFEST: library/ai-parts.json, with one-block characters expanded into their sections.

An entry with "kind": "body" is a whole generated figure. It names its paint colours once (classes -> sRGB samples)
and the sheet for each class; this module expands it into the standard sections, each a normal entry that
tools/ai_part.py prepares and part_registry registers:

    "<prefix>_torso" "<prefix>_sleeve_L" "<prefix>_sleeve_R" "<prefix>_hakama" "<prefix>_leg_L" "<prefix>_leg_R"
    "<prefix>_foot_L" "<prefix>_foot_R"  (+ "<prefix>_head" when "head": true)

The boxes are in rig metres after the body fit (feet at 0, the shoulder line at 1.40 m), proven on Kojiro
(kojiro_*_t1, 27 Nov: 152/152, bends through the 5-pose sweep). A section may only contain the classes listed for
it in SECTIONS (or the block's own "classes": {section: [...]}), so a sleeve can never pick up hakama paint.
A block may also list its "sections" (a subset of ORDER: a kimono to the floor has no legs to cut, so the
"hakama" section keeps the whole skirt) and override per section "keep", "faces" and "bind" (bones / layer). Used by tools/ai_part.py and part_registry.load_ai_parts().
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
MANIFEST = os.path.join(REPO, 'library', 'ai-parts.json')

# section: (slot, socket, keep box, faces, classes it may contain, binding)
SECTIONS = {
    'torso':    ('torso', 'chest', {'x': [-0.215, 0.215], 'z': [0.86, 1.50]}, 5000,
                 ['robe', 'under', 'obi', 'hakama'], {'bones': ['hips', 'torso', 'upper']}),
    'sleeve_L': ('sleeve_upper', 'shoulder.L', {'x': [0.20, 0.75], 'z': [0.92, 1.55]}, 2500,
                 ['robe', 'under'], {'bones': ['lS', 'lT']}),
    'sleeve_R': ('sleeve_upper', 'shoulder.R', {'x': [-0.75, -0.20], 'z': [0.92, 1.55]}, 2500,
                 ['robe', 'under'], {'bones': ['lS', 'lT']}),
    'hakama':   ('armor', 'obi', {'x': [-0.32, 0.32], 'z': [0.52, 0.93]}, 3000,
                 ['hakama', 'obi'], {'bones': ['hips', 'lthigh', 'rthigh'], 'layer': 52}),
    'leg_L':    ('shin', 'knee.L', {'x': [0.0, 0.40], 'z': [0.12, 0.56]}, 2500,
                 ['hakama', 'obi'], {'bones': ['lthigh', 'lshin', 'hips']}),
    'leg_R':    ('shin', 'knee.R', {'x': [-0.40, 0.0], 'z': [0.12, 0.56]}, 2500,
                 ['hakama', 'obi'], {'bones': ['lthigh', 'lshin', 'hips']}),
    'foot_L':   ('foot', 'ankle.L', {'x': [0.0, 0.35], 'z': [-0.02, 0.15]}, 900,
                 ['tabi', 'straw', 'obi'], {'rigid': True, 'bone': 'lfoot'}),
    'foot_R':   ('foot', 'ankle.R', {'x': [-0.35, 0.0], 'z': [-0.02, 0.15]}, 900,
                 ['tabi', 'straw', 'obi'], {'rigid': True, 'bone': 'rfoot'}),
    'head':     ('face', 'face', {'x': [-0.20, 0.20], 'z': [1.47, 2.10]}, 4000,
                 ['skin', 'hair', 'band'], {'rigid': True, 'bone': 'head'}),
}
ORDER = ['torso', 'sleeve_L', 'sleeve_R', 'hakama', 'leg_L', 'leg_R', 'foot_L', 'foot_R', 'head']


def expand_body(prefix, b):
    out = {}
    fit = b.get('fit') or {'mode': 'body', 'shoulder_frac': 0.74, 'shoulder_z': 1.40}
    colors, sheets = b['colors'], b['sheets']
    only = b.get('sections')                           # a figure without every section (a kimono has no legs to cut)
    for sec in ORDER:
        if sec == 'head' and not b.get('head'):
            continue
        if only is not None and sec not in only:
            continue
        slot, socket, keep, faces, classes, bind = SECTIONS[sec]
        faces = b.get('faces', {}).get(sec, faces)         # a long robe skirt needs more facets than a hakama top
        bind = dict(bind, **b.get('bind', {}).get(sec, {}))  # e.g. a floor-length skirt also follows the shins
        classes = b.get('classes', {}).get(sec, classes)   # an outfit that is not a kimono (armour: red lacing on the skirt)
        keep = dict(keep, **(b.get('keep', {}).get(sec, {})))
        pal = [{'name': c, 'rgb': colors[c]} for c in classes if c in colors]
        e = {'label': f'{b.get("label", prefix)}: {sec.replace("_", " ")}', 'slot': slot, 'socket': socket,
             'raw': b['raw'], 'facing': b.get('facing', '+x'), 'fit': fit, 'source': b.get('source', {}),
             'prepared': f'assets/models/ai/{prefix}_{sec}', 'keep': keep, 'faces': faces, 'palette': pal,
             'sheets': {p['name']: sheets[p['name']] for p in pal}, 'rigid': bool(bind.get('rigid', False)),
             'from_body': prefix}
        for k in ('bones', 'bone', 'layer', 'skin'):     # skin: 'skirt' = by height and side (a long robe)
            if k in bind:
                e[k] = bind[k]
        for k in ('cage', 'ray', 'bake_res'):          # bake settings shared by every section of the body
            if k in b:
                e[k] = b[k]
        if sec in b.get('shift', {}):                  # a section moved after it is cut and painted (rig metres)
            e['shift'] = b['shift'][sec]
        zones = {c: z for c, z in b.get('zones', {}).items() if c in classes}
        if zones:                                       # where on the body each class may be (rig metres)
            e['zones'] = zones
        if sec == 'head':
            e.update({k: v for k, v in b.get('head_extra', {}).items()})
        out[f'{prefix}_{sec}'] = e
    return out


def load(path=MANIFEST):
    """The manifest with every body block expanded (body blocks themselves are dropped from the result)."""
    raw = json.load(open(path))
    out = {}
    for k, e in raw.items():
        if k.startswith('_') or not isinstance(e, dict):
            continue
        if e.get('kind') == 'body':
            out.update(expand_body(k, e))
        else:
            out[k] = e
    return out
