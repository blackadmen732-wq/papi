"""LINE-UP: several recipes side by side, one camera, one light, so a cast is judged together (scale, colour, read).

    B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
    $B -b -P blender/character/lineup.py -- \
        --recipes ronin-ai,kojiro-ai2,noblewoman-ai,monk-ai,assassin-ai,samurai-ai \
        --labels Ronin,Samurai,Noblewoman,Monk,Assassin,Warrior \
        --out output/cast/lineup.png [--res 1280x720] [--samples 32] [--light neutral|cinematic] [--pose neutral]

Recipes are names in library/character-recipes/ (or paths). Each figure stands on a mark `--gap` metres apart
(default 0.95), facing the camera; the camera frames the whole row at the figures' mid height. --labels writes
<out>-labels.json (figure order and x position) for the report; the picture itself carries no text.
"""
import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import modular_builder as MB  # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index('--' + n) + 1] if '--' + n in ARGV else d


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    names = arg('recipes').split(',')
    labels = arg('labels', '').split(',') if arg('labels') else names
    gap = float(arg('gap', 0.95))
    pose = arg('pose', 'neutral')
    xs = [(i - (len(names) - 1) / 2) * gap for i in range(len(names))]
    objs = []
    for nm, x in zip(names, xs):
        p = nm if nm.endswith('.json') else os.path.join(REPO, 'library', 'character-recipes', nm + '.json')
        r = MB.load_recipe(os.path.abspath(p))
        ch = MB.build(r, pose=pose, location=(x, 0, 0), name=r.get('id', nm),
                      pose_overrides=r.get('pose_overrides') if pose == 'neutral' else None)
        objs += ch['objects']
    MB.studio(scene, arg('light', 'neutral'))
    MB.render_settings(scene, arg('res', '1280x720'), int(arg('samples', 32)))
    # ground: a plain floor so the feet read as standing
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    fl = bpy.context.object
    m = bpy.data.materials.new('floor')
    m.use_nodes = True
    m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.32, 0.31, 0.3, 1)
    fl.data.materials.append(m)
    centre, height = MB.frame(objs)
    width = xs[-1] - xs[0] + gap
    lens = float(arg('lens', 50))
    x0, y0 = map(int, arg('res', '1280x720').split('x'))
    # distance so the row fills ~92% of the frame width (36 mm sensor across the wider side)
    fov_w = 2 * math.atan(18.0 / lens) if x0 >= y0 else 2 * math.atan(18.0 * x0 / y0 / lens)
    d = max(width / 0.92 / (2 * math.tan(fov_w / 2)), height * 1.6)
    MB.camera(scene, (0, -d, centre[2] + 0.15), (0, 0, centre[2]), lens)
    out = os.path.abspath(arg('out', 'output/cast/lineup.png'))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    MB.render(scene, out)
    with open(out[:-4] + '-labels.json', 'w') as fh:
        json.dump([{'label': l, 'recipe': n, 'x': x} for l, n, x in zip(labels, names, xs)], fh, indent=1)
    print('wrote', out)


if __name__ == '__main__':
    main()
