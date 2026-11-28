"""CHECK MARKS: is the ground flat where a film will stand its fighters? For every MARK_* of a built set, cast rays
down on a grid around the mark (the same rule as blender/production_bake.py ground_sampler: the highest UP-facing hit
on any visible mesh that is not the sea, the sky, a character or a weapon) and report the height range, the worst
slope between neighbours and any hole (no ground) in the patch.

  B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
  $B -b output/sets/palace-island.blend -P blender/sets/check_marks.py -- [--radius 3] [--step 0.5] [--tol 0.05]

Exit code 1 when a mark's patch spans more than `tol` metres or has a hole.
"""
import math
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d):
    return float(ARGV[ARGV.index('--' + n) + 1]) if '--' + n in ARGV else d


R, STEP, TOL = arg('radius', 3.0), arg('step', 0.5), arg('tol', 0.05)
SKIP_KITS = ('fog', 'particles', 'rain', 'moon', 'layers')


def sampler(sc):
    dg = bpy.context.evaluated_depsgraph_get()
    obs = [o for o in sc.objects if o.type == 'MESH' and o.visible_get() and len(o.data.polygons)
           and not o.name.startswith(('SEA', 'SKY', 'PC_', 'MARK_', 'KATANA_', 'BOKKEN_', 'CLOUD', 'MOUNTAINS'))
           and o.get('pc_kit') not in SKIP_KITS and not any(c.name == 'CHARACTERS' for c in o.users_collection)]
    trees = [(o.name, o.matrix_world.copy(), o.matrix_world.inverted(), BVHTree.FromObject(o, dg)) for o in obs]

    def at(x, y, z_from):
        best = None
        for name, M, Mi, t in trees:
            hit = t.ray_cast(Mi @ Vector((x, y, z_from)), (Mi.to_3x3() @ Vector((0, 0, -1))).normalized(), 80.0)
            if hit[0] is not None and (M.to_3x3() @ hit[1]).normalized().z > 0.5:
                z = (M @ hit[0]).z
                if best is None or z > best[0]:
                    best = (z, name)
        return best
    return at


def main():
    sc = bpy.context.scene
    at = sampler(sc)
    bad = 0
    marks = [o for o in bpy.data.objects if o.name.startswith('MARK_')]
    for m in sorted(marks, key=lambda o: o.name):
        c = m.matrix_world.translation
        n = int(R / STEP)
        zs, holes, names = {}, 0, set()
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                if math.hypot(i, j) * STEP > R:
                    continue
                h = at(c.x + i * STEP, c.y + j * STEP, c.z + 2.5)
                if h is None:
                    holes += 1
                else:
                    zs[(i, j)] = h[0]
                    names.add(h[1])
        if not zs:
            print(f'{m.name}: NO GROUND within {R} m')
            bad += 1
            continue
        vals = list(zs.values())
        slope = 0.0
        for (i, j), z in zs.items():
            for di, dj in ((1, 0), (0, 1)):
                z2 = zs.get((i + di, j + dj))
                if z2 is not None:
                    slope = max(slope, math.degrees(math.atan(abs(z2 - z) / STEP)))
        span = max(vals) - min(vals)
        ok = span <= TOL and holes == 0
        bad += not ok
        print(f'{m.name} at ({c.x:.2f}, {c.y:.2f}, {c.z:.2f}): {len(vals)} samples within {R} m, z {min(vals):.3f}..{max(vals):.3f} '
              f'(span {span * 100:.1f} cm), steepest {slope:.1f} deg, holes {holes}, on {sorted(names)} -> {"FLAT" if ok else "NOT FLAT"}')
    sys.exit(1 if bad else 0)


main()
