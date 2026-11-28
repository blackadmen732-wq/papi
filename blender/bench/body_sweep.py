"""BODY SWEEP: does the paper body bend cleanly on the skeleton? (Mark, 28 Nov: "fix the leg, the skeleton, the
whole articulation and the body".)

  B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
  $B -b -t 2 -P blender/bench/body_sweep.py -- --recipe library/character-recipes/kojiro-ai2.json \
      --out output/body/kojiro [--poses all | extreme | a,b,c] [--render] [--res 300] [--samples 8]
  python3 blender/bench/body_sweep.py --sheet output/body/kojiro        # one contact sheet of the rendered poses

Builds the character from a recipe (modular_builder.build), puts it through poses and measures, per pose:
  knee        the bend of each knee (deg) and the soft-IK stretch of each leg (1.0 = no stretch)
  sole        the lowest point of each rigid foot part above the ground (cm; < 0 = in the ground)
  heel / toe  how far each heel and toe tip is off the ground (cm): a planted foot keeps its toes down
  arm_in      how deep the arm (shoulder to wrist, the first 10 cm skipped) goes into the BODY under the clothes
              (blender/character/body_capsules.py, shrink 0.035): > 0 cm = the arm is inside the person
  tear        the worst edge stretch of every skinned part, posed length / rest length, and how many edges more
              than doubled or fell under a quarter (a crease that folds back through itself)
  through     arm-part (sleeve, forearm, hand) vertices inside the TORSO paper (nearest-surface test), cm deep
Writes <out>.json (every number) and, with --render, <out>-<pose>.png per pose from one fixed 3/4 camera.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))

EXTREME = {
    # the extreme sweep (task 3): a deep lunge, a kneel, arms overhead, a twist, plus the poses the films hold
    'lunge-deep': {'stance': 1.05, 'crouch': 0.42, 'weight': 0.55, 'rsx': -1.4, 'lsx': -1.3, 'tx': 0.35,
                   'rex': -0.4, 'lex': -0.5},
    'kneel': {'stance': 0.5, 'crouch': 0.5, 'weight': 0.2, 'rsx': -0.5, 'lsx': -0.5, 'tx': 0.1,
              'rex': -1.2, 'lex': -1.2},
    'arms-overhead': {'stance': 0.3, 'crouch': 0.02, 'rsx': -3.0, 'lsx': -3.0, 'rsz': 0.25, 'lsz': -0.25,
                      'rex': -0.2, 'lex': -0.2},
    'twist': {'stance': 0.55, 'crouch': 0.12, 'ty': 0.7, 'cy': 0.45, 'rsx': -1.2, 'lsx': -0.9, 'rex': -0.8,
              'lex': -1.2, 'hy': -0.6},
}
SWEEP5 = ['neutral', 'jodan', 'crouch-load', 'airborne-guard', 'kesa-finish']


def sheet(prefix):
    """Contact sheet of <prefix>-<pose>.png (system python, PIL)."""
    from PIL import Image, ImageDraw
    d = json.load(open(prefix + '.json'))
    names = [n for n in d['order'] if os.path.exists(f'{prefix}-{n}.png')]
    ims = [Image.open(f'{prefix}-{n}.png').convert('RGB') for n in names]
    if not ims:
        print('no renders under', prefix)
        return
    w, h = ims[0].size
    cols = min(6, len(ims))
    rows = (len(ims) + cols - 1) // cols
    S = Image.new('RGB', (cols * w, rows * (h + 18)), (30, 30, 30))
    dr = ImageDraw.Draw(S)
    for i, (n, im) in enumerate(zip(names, ims)):
        x, y = (i % cols) * w, (i // cols) * (h + 18)
        S.paste(im, (x, y + 18))
        r = d['poses'][n]
        dr.text((x + 4, y + 3), '%s  knee %.0f/%.0f  arm %.1f' % (n, r['knee']['r'], r['knee']['l'],
                                                                  max(r['arm_in'].values())), fill=(240, 240, 240))
    S.save(prefix + '-sheet.png')
    print('wrote', prefix + '-sheet.png')


if 'bpy' not in sys.modules and '--sheet' in sys.argv:
    sheet(sys.argv[sys.argv.index('--sheet') + 1])
    sys.exit(0)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

sys.path.insert(0, os.path.join(REPO, 'blender', 'character'))
import body_capsules as BC  # noqa: E402
import modular_builder as MB  # noqa: E402

arg, flag = MB.arg, MB.flag


def edges_world(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    M = ev.matrix_world
    co = [M @ v.co for v in me.vertices]
    ed = [tuple(e.vertices) for e in me.edges]
    ev.to_mesh_clear()
    return co, ed


def mesh_bvh(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    M = ev.matrix_world
    verts = [M @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys, epsilon=0.0)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    recipe = MB.load_recipe(os.path.abspath(arg('recipe')))
    ch = MB.build(recipe, pose='neutral', pose_overrides=recipe.get('pose_overrides'))
    rig = ch['rig']
    sel = arg('poses', 'all')
    if sel == 'all':
        order = SWEEP5 + list(EXTREME) + [n for n in MB.POSES if isinstance(MB.POSES[n], dict)
                                          and n not in SWEEP5 and not n.startswith('_')]
    elif sel == 'extreme':
        order = SWEEP5 + list(EXTREME) + ['zanshin', 'kneel-collapse', 'low-dodge', 'drive-contact', 'tsuki-thrust']
    else:
        order = sel.split(',')
    objs = [o for o in ch['objects'] if o.type == 'MESH' and len(o.data.vertices)]
    skinned = [o for o in objs if any(m.type == 'ARMATURE' for m in o.modifiers)]
    feet = [o for o in objs if o.get('pc_socket', '').startswith('ankle') or 'foot' in o.get('pc_recipe', '')]
    slot = lambda o: MB.reg.PARTS.get(o.get('pc_recipe', ''), {}).get('slot', '')
    arms = [o for o in objs if slot(o) in ('sleeve_upper', 'sleeve_hanging', 'forearm', 'hand')]
    torso = [o for o in objs if slot(o) == 'torso']
    # rest edge lengths (built in the neutral pose: measure the REST by posing the rig at rest angles)
    dg = bpy.context.evaluated_depsgraph_get()
    rest_len = {}
    for o in skinned:
        mod = [m for m in o.modifiers if m.type == 'ARMATURE'][0]
        mod.show_viewport = False
        dg.update()
        co, ed = edges_world(o, dg)
        rest_len[o.name] = [max((co[a] - co[b]).length, 1e-6) for a, b in ed]
        mod.show_viewport = True
    caps = BC.BodyCapsules(rig, shrink=0.035)
    if flag('render'):
        MB.studio(scene, arg('light', 'neutral'))
        r = int(arg('res', 300))
        MB.render_settings(scene, f'{r}x{int(r * 1.6)}', int(arg('samples', 8)))
    out = arg('out', 'output/body/sweep')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    res = {'recipe': recipe.get('id'), 'order': order, 'poses': {}}
    for nm in order:
        p = EXTREME.get(nm, nm)
        rig.pose(p, **(recipe.get('pose_overrides', {}) if nm == 'neutral' else {}))
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        J = rig.J
        R = {}
        knee, stretch = {}, {}
        for s in ('r', 'l'):
            h, k, a = (J[s + j].matrix_world.translation for j in ('thigh', 'shin', 'foot'))
            knee[s] = round(math.degrees((k - h).angle(a - k, 0.0)), 1)
            stretch[s] = round(J[s + 'thigh'].matrix_world.to_scale()[0], 4)
        R['knee'], R['stretch'] = knee, stretch
        sole, heel, toe = {}, {}, {}
        for o in feet:
            side = 'l' if o.get('pc_socket', '').endswith('L') else 'r'
            co, _ = edges_world(o, dg)
            zs = [c.z for c in co]
            sole[side] = round(min(zs) * 100, 1)
            fwd = (J[side + 'foot'].matrix_world.to_3x3() @ Vector((0, -1, 0)))
            fwd.z = 0
            fwd = fwd.normalized() if fwd.length > 1e-6 else Vector((0, -1, 0))
            proj = [c.dot(fwd) for c in co]
            lo, hi = min(proj), max(proj)
            heel[side] = round(min(c.z for c, q in zip(co, proj) if q < lo + 0.04) * 100, 1)
            toe[side] = round(min(c.z for c, q in zip(co, proj) if q > hi - 0.04) * 100, 1)
        R['sole'], R['heel'], R['toe'] = sole, heel, toe
        caps.update()
        arm_in = {}
        for s in ('r', 'l'):
            worst = -1.0
            pts = []
            for a_, b_ in ((s + 'S', s + 'E'), (s + 'E', s + 'H')):
                A, B_ = J[a_].matrix_world.translation, J[b_].matrix_world.translation
                for i in range(11):
                    pts.append(A.lerp(B_, i / 10))
            S0 = J[s + 'S'].matrix_world.translation
            for q in pts:
                if (q - S0).length < 0.10:
                    continue
                dpt, who = caps.depth(q, skip=tuple(n for n in [c[0] for c in BC.CAPSULES] if n.startswith(('upperarm', 'forearm', 'shoulders', 'head', 'thigh', 'shin'))))
                worst = max(worst, dpt)
            arm_in[s] = round(max(0.0, worst) * 100, 1)
        R['arm_in'] = arm_in
        tear = {}
        for o in skinned:
            co, ed = edges_world(o, dg)
            rl = rest_len[o.name]
            ratios = [(co[a] - co[b]).length / l0 for (a, b), l0 in zip(ed, rl)]
            ratios.sort()
            n = len(ratios)
            tear[o.name] = {'max': round(ratios[-1], 2), 'p99': round(ratios[int(n * 0.99) - 1], 2),
                            'over2': sum(1 for r_ in ratios if r_ > 2.0),
                            'under.25': sum(1 for r_ in ratios if r_ < 0.25)}
        R['tear'] = tear
        R['tear_worst'] = max((t['max'] for t in tear.values()), default=0)
        R['tear_over2'] = sum(t['over2'] for t in tear.values())
        through = {}
        if torso:
            bv = [mesh_bvh(t, dg) for t in torso]
            for o in arms:
                co, _ = edges_world(o, dg)
                deep, cnt = 0.0, 0
                for c in co:
                    for b in bv:
                        hit = b.find_nearest(c, 0.12)
                        if hit[0] is None:
                            continue
                        dd = (c - hit[0]).dot(hit[1])
                        if dd < -0.01:                 # behind the torso surface by more than 1 cm
                            cnt += 1
                            deep = max(deep, -dd)
                            break
                through[o.name] = {'n': cnt, 'of': len(co), 'cm': round(deep * 100, 1)}
        R['through'] = through
        R['through_n'] = sum(t['n'] for t in through.values())
        res['poses'][nm] = R
        print('[sweep] %-20s knee r %5.1f l %5.1f  stretch %.3f/%.3f  sole %s  heel %s toe %s  arm_in %s  '
              'tear %.2f (%d)  through %d' % (nm, knee['r'], knee['l'], stretch['r'], stretch['l'], sole, heel, toe,
                                              arm_in, R['tear_worst'], R['tear_over2'], R['through_n']))
        if flag('render'):
            c2, h2 = MB.frame(ch['objects'])
            a = math.radians(float(arg('angle', 34)))
            d2 = 2.0 * 2.55
            MB.camera(scene, (-math.sin(a) * d2, -math.cos(a) * d2, 1.0), (0, 0, float(arg('look', 0.85))), float(arg('lens', 60)))
            MB.render(scene, f'{out}-{nm}.png')
    with open(out + '.json', 'w') as fh:
        json.dump(res, fh, indent=1)
    ps = res['poses'].values()
    print('[sweep] SUMMARY %s: %d poses  knee neutral r %.1f l %.1f | worst stretch %.3f | worst arm_in %.1f cm | '
          'worst tear %.2f, edges >2x %d | arm vertices in the torso %d | lowest sole %.1f cm' % (
              res['recipe'], len(order), res['poses'][order[0]]['knee']['r'], res['poses'][order[0]]['knee']['l'],
              max(max(r['stretch'].values()) for r in ps), max(max(r['arm_in'].values()) for r in ps),
              max(r['tear_worst'] for r in ps), sum(r['tear_over2'] for r in ps), sum(r['through_n'] for r in ps),
              min(min(r['sole'].values() or [0]) for r in ps)))
    print('wrote', out + '.json')


main()
