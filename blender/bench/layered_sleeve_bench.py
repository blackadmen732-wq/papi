"""LAYERED SLEEVE BENCH: today's generated sleeve against the layered one (AUTOPILOT item 17), on the REAL sleeve
meshes, on the SAME baked motion: Kojiro's sword arm in Episode 1 (31.5-35 s: the charge and the strike).

  B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
  $B -b -P blender/bench/layered_sleeve_bench.py -- --film ganryujima-ep1 [--actor hero] [--from 31.5] [--to 35.0] \
       [--today kojiro-ai2] [--layered kojiro-ai2-layered] [--res 480x640] [--samples 8] [--no-render] \
       [--out output/bench/layered]

Both characters are built from their recipes and driven by the SAME joints, frame by frame, from the production
bake (output/<film>.bake.json `rec['J']`: what the film renders). TODAY's sleeve is skinned to the arm (it rides
it); the LAYERED sleeve's hanging part is 4 paper plates on a joint chain (blender/character/layered_garment.py),
each on its own spring (blender/character/cloth_springs.plate_springs), the plates' corners kept out of the body.
Measured every frame (report.json):
  inside_cm     how deep any vertex of the sleeve paper sinks into the PERSON (body_capsules, shrink 0.035, the arm
                it hangs from not counted: the bake's own 'sleeve-paper' check)
  plate_deg     each plate's direction against where its arm would carry it (0 = riding the arm like today)
  bend_deg      each plate against the plate above it (plate 0 against the forearm)
  ripple_deg    the last plate's direction against the first's
  lag           when each plate's swing peaks, and the cross-correlation lag of plate j's swing behind plate j-1's
Renders each frame twice from the same camera (one character hidden each time), side by side, labelled; an mp4 and
a contact sheet (every 4th frame) for watching.
"""
import json
import math
import os
import shutil
import statistics
import subprocess
import sys

import bpy
from mathutils import Euler, Vector

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for d in ('blender', 'blender/character', 'blender/world'):
    sys.path.insert(0, os.path.join(REPO, d))
import modular_builder as MB  # noqa: E402
import body_capsules as BC  # noqa: E402
import cloth_springs as CS  # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
DOWN = Vector((0.0, 0.0, -1.0))


def arg(n, d=None):
    return ARGV[ARGV.index('--' + n) + 1] if '--' + n in ARGV else d


def flag(n):
    return '--' + n in ARGV


def ang(a, b):
    return math.degrees(a.normalized().angle(b.normalized(), 0.0))


def main():
    film = arg('film', 'ganryujima-ep1')
    actor = arg('actor', 'hero')
    out = os.path.join(REPO, arg('out', 'output/bench/layered'))
    B = json.load(open(os.path.join(REPO, 'output', film + '.bake.json')))
    fps = float(B.get('fps', 30))
    JJ = B['actors'][actor]['J']
    f0 = int(round(float(arg('from', 31.5)) * fps))
    f1 = min(len(JJ) - 1, int(round(float(arg('to', 35.0)) * fps)))
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    sc = bpy.context.scene
    rd = os.path.join(REPO, 'library', 'character-recipes')
    chars = {}
    for key, rid in (('today', arg('today', 'kojiro-ai2')), ('layered', arg('layered', 'kojiro-ai2-layered'))):
        chars[key] = MB.build(MB.load_recipe(os.path.join(rd, rid + '.json')), pose='standing', name=key.upper())
    rigL, rigT = chars['layered']['rig'], chars['today']['rig']
    springs = CS.ClothSprings(rigL, BC.BodyCapsules(rigL), fps=fps, springs=(), panels={},
                              body=BC.BodyCapsules(rigL, shrink=0.035))
    FJ = json.load(open(os.path.join(REPO, 'film', film + '.json')))
    if FJ.get('wind'):                     # the film's wind, passed as film_modular passes it (film x/z -> world x/-z)
        springs.wind = dict(FJ['wind'], to=[float(FJ['wind']['to'][0]), -float(FJ['wind']['to'][1])])
    if not springs.spec:
        raise SystemExit('the layered recipe made no plate joints')
    print('[bench] plate springs:', [(s[0], round(s[1], 3), round(s[2], 1)) for s in springs.spec])
    person = {k: BC.BodyCapsules(c['rig'], shrink=0.035) for k, c in chars.items()}
    sleeves = {k: [o for o in c['objects'] if o.type == 'MESH' and 'sleeve' in o.get('pc_recipe', '')]
               for k, c in chars.items()}
    sides = sorted({str(e['pc_plate_side']) for e in rigL.J.values() if 'pc_plate' in e})
    plates = {sd: sorted([n for n, e in rigL.J.items() if 'pc_plate' in e and e['pc_plate_side'] == sd],
                         key=lambda n: rigL.J[n]['pc_plate']) for sd in sides}

    render = not flag('no-render')
    if render:
        MB.studio(sc, 'neutral')
        MB.render_settings(sc, arg('res', '480x640'), int(arg('samples', 8)))
        cam = MB.camera(sc, (0, -4, 1.3), (0, 0, 1.2), lens=45)
        fdir = os.path.join(out, 'frames')
        shutil.rmtree(fdir, ignore_errors=True)
        os.makedirs(fdir, exist_ok=True)
    rep = {'film': film, 'actor': actor, 'frames': [f0, f1], 'fps': fps, 'today': arg('today', 'kojiro-ai2'),
           'layered': arg('layered', 'kojiro-ai2-layered'),
           'springs': [list(s[:5]) for s in springs.spec], 'per_frame': []}
    view = None
    follow = None
    for f in range(f0, f1 + 1):
        Jf = JJ[f]
        if Jf is None:
            continue
        for c in chars.values():
            for n, v in Jf.items():
                if n in c['rig'].J:
                    c['rig'].J[n].location = v[:3]
                    c['rig'].J[n].rotation_euler = v[3:6]
        bpy.context.view_layer.update()
        springs.step()                       # rests every plate on its parent, then swings it (and clears the body)
        for c in chars.values():
            c['rig'].sync_bones()
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        row = {'f': f}
        for k, c in chars.items():
            person[k].update()
            worst = {}
            for ob in sleeves[k]:
                sd = 'R' if ob.get('pc_socket', '').endswith('.R') else 'L'
                me = ob.evaluated_get(dg).to_mesh()
                mw = ob.matrix_world
                w = worst.get(sd, 0.0)
                for vv in me.vertices:
                    d_, _who = person[k].depth(mw @ vv.co, skip=('upperarm.' + sd, 'forearm.' + sd))
                    w = max(w, d_)
                worst[sd] = w
                ob.evaluated_get(dg).to_mesh_clear()
            row['inside_cm_' + k] = {sd: round(max(0.0, w) * 100, 2) for sd, w in worst.items()}
        bw = {}
        for ob in sleeves['layered']:
            if 'pc_band' not in ob:
                continue
            sd = 'R' if ob.get('pc_socket', '').endswith('.R') else 'L'
            for vv in ob.data.vertices:            # rigid bands: the mesh is the evaluated mesh
                d_, _who = person['layered'].depth(ob.matrix_world @ vv.co, skip=('upperarm.' + sd, 'forearm.' + sd))
                bw[sd] = max(bw.get(sd, 0.0), d_)
        row['inside_cm_plates'] = {sd: round(max(0.0, w) * 100, 2) for sd, w in bw.items()}
        for sd, names in plates.items():
            fore = rigL.J[sd.lower() + 'T']
            carried = None
            pd, bd, dirs = [], [], []
            prev = None
            for n in names:
                e = rigL.J[n]
                d = (e.matrix_world.to_quaternion() @ DOWN).normalized()
                if carried is None:              # where the forearm would carry plate 0 (and the whole chain)
                    carried = (fore.matrix_world.to_quaternion() @ Euler(tuple(e['pc_rest_rot']), 'YZX').to_quaternion()
                               @ DOWN).normalized()
                pd.append(round(ang(d, carried), 2))
                bd.append(round(ang(d, prev if prev is not None else carried), 2))
                dirs.append(d)
                prev = d
            row['plate_deg_' + sd] = pd
            row['bend_deg_' + sd] = bd
            row['ripple_deg_' + sd] = round(ang(dirs[0], dirs[-1]), 2)
            h_ = rigL.J[names[0]].matrix_world.translation
            row['hinge_inside_cm_' + sd] = round(100 * max(0.0, person['layered'].depth(
                h_, skip=('upperarm.' + sd, 'forearm.' + sd))[0]), 2)
            row['dirs_' + sd] = [[round(x, 5) for x in d_] for d_ in dirs] + [[round(x, 5) for x in carried]]
        rep['per_frame'].append(row)
        if render:
            # the camera: three-quarter front-right of the actor (fixed at the first frame's facing), following the
            # chest softly; both characters stand on the same spot, rendered one at a time from the same camera
            rq = rigT.J['root'].matrix_world.to_quaternion()
            chest = rigT.J['upper'].matrix_world.translation.copy()
            if view is None:
                fwd = (rq @ Vector((0, -1, 0)))
                rgt = (rq @ Vector((-1, 0, 0)))
                view = Vector((fwd.x * 0.55 + rgt.x * 0.85, fwd.y * 0.55 + rgt.y * 0.85, 0.0)).normalized()
            follow = chest.copy() if follow is None else follow.lerp(chest, 0.35)
            look = follow + Vector((0, 0, -0.05))
            cam.location = look + view * 3.6 + Vector((0, 0, 0.25))
            cam.rotation_euler = (look - cam.location).to_track_quat('-Z', 'Y').to_euler()
            for k in chars:
                for k2, c2 in chars.items():
                    for o in c2['collection'].all_objects:
                        o.hide_render = (k2 != k)
                MB.render(sc, os.path.join(fdir, '%s_%04d.png' % (k, f - f0 + 1)))
        print('[bench] f%d inside today %s layered %s ripple R %s' % (
            f, row['inside_cm_today'], row['inside_cm_layered'], row.get('ripple_deg_R')))

    # ---- summary
    S = {}
    pf = rep['per_frame']
    for sd in ('R', 'L'):
        xs = [r.get('inside_cm_plates', {}).get(sd, 0.0) for r in pf]
        S['inside_plates_%s' % sd] = {'frames_over_0.5cm': sum(1 for x in xs if x > 0.5),
                                      'frames_over_0': sum(1 for x in xs if x > 0), 'deepest_cm': max(xs)}
    for k in chars:
        for sd in ('R', 'L'):
            xs = [r['inside_cm_' + k].get(sd, 0.0) for r in pf]
            S['inside_%s_%s' % (k, sd)] = {'frames_over_0.5cm': sum(1 for x in xs if x > 0.5),
                                           'frames_over_0': sum(1 for x in xs if x > 0), 'deepest_cm': max(xs)}
    for sd in plates:
        n = len(plates[sd])
        S['ripple_%s' % sd] = {'median_deg': statistics.median(r['ripple_deg_' + sd] for r in pf),
                               'max_deg': max(r['ripple_deg_' + sd] for r in pf)}
        series = [[r['plate_deg_' + sd][j] for r in pf] for j in range(n)]
        bends = [[r['bend_deg_' + sd][j] for r in pf] for j in range(n)]
        S['plate_%s' % sd] = [{'plate': j, 'median_deg': round(statistics.median(series[j]), 1),
                               'max_deg': max(series[j]), 'peak_frame': f0 + series[j].index(max(series[j])),
                               'bend_median_deg': round(statistics.median(bends[j]), 1), 'bend_max_deg': max(bends[j])}
                              for j in range(n)]
        # cross-correlation lag: how many frames plate j's swing trails plate j-1's (the swing's change per frame)
        lags = []
        for j in range(1, n):
            a = [series[j - 1][i + 1] - series[j - 1][i] for i in range(len(pf) - 1)]
            b = [series[j][i + 1] - series[j][i] for i in range(len(pf) - 1)]
            best = (-1e9, 0)
            for L in range(0, 9):
                s_ = sum(a[i] * b[i + L] for i in range(len(a) - L))
                best = max(best, (s_, L))
            lags.append(best[1])
        S['peak_corr_lag_frames_%s' % sd] = lags
        # the real test of "each plate trails the one above": plate j's world direction now against the direction
        # the plate above (the forearm's carried direction for plate 0) had tau frames ago; the tau that matches best,
        # on the frames where the arm is moving (the carried direction turns > 3 deg per frame)
        D = [[Vector(r['dirs_' + sd][j]) for r in pf] for j in range(n + 1)]   # D[n] = carried by the forearm
        moving = [i for i in range(1, len(pf)) if ang(D[n][i], D[n][i - 1]) > 3.0]
        shift = []
        for j in range(n):
            above = D[n] if j == 0 else D[j - 1]
            errs = []
            for tau in range(0, 9):
                xs = [ang(D[j][i], above[i - tau]) for i in moving if i - tau >= 0]
                errs.append(round(statistics.mean(xs), 2) if xs else 1e9)
            best = errs.index(min(errs))
            shift.append({'plate': j, 'best_tau_frames': best, 'mean_deg_at_best': errs[best], 'mean_deg_at_0': errs[0]})
        S['trail_%s' % sd] = {'moving_frames': len(moving), 'plates': shift}
        # trailing as the paper shows it: on the frames the arm moves, is each plate further behind the aim than the
        # plate above it? (fraction of moving frames, and the median deflection of each plate on those frames)
        S['trail_order_%s' % sd] = {
            'median_deg_moving': [round(statistics.median(series[j][i] for i in moving), 1) for j in range(n)],
            'frac_behind_above': [round(sum(1 for i in moving if series[j][i] >= series[j - 1][i]) / max(1, len(moving)), 2)
                                  for j in range(1, n)],
            'median_deg_still': [round(statistics.median(series[j][i] for i in range(len(pf)) if i not in moving), 1)
                                 for j in range(n)]}
        hi = [r['hinge_inside_cm_' + sd] for r in pf]
        S['hinge_inside_%s' % sd] = {'frames': sum(1 for x in hi if x > 0), 'deepest_cm': max(hi)}
        # plate depth on frames whose hinge is OUTSIDE the body (what the plates themselves are responsible for)
        xs = [r.get('inside_cm_plates', {}).get(sd, 0.0) for r in pf if r['hinge_inside_cm_' + sd] <= 0]
        S['inside_plates_hinge_out_%s' % sd] = {'frames': len(xs), 'frames_over_0': sum(1 for x in xs if x > 0),
                                               'deepest_cm': max(xs) if xs else 0.0}
    S['hinge_inside_events'] = len(springs.hinge_inside)
    rep['summary'] = S
    os.makedirs(out, exist_ok=True)
    json.dump(rep, open(os.path.join(out, 'report.json'), 'w'), indent=1)
    print('[bench] summary', json.dumps(S, indent=1))
    print('[bench] wrote', os.path.join(out, 'report.json'))


if __name__ == '__main__':
    main()
