"""PAPERIZE A SET: the characters' paper surface (paper_materials.add_fold_lines + paper_surface: ink in the valleys of
every fold, a light edge on the ridges, a printed mottle, soft occlusion in the folds) on every building mesh of a
built set, at ARCHITECTURE scale, then render its camera anchors. Mark, 28 Nov: the palace "with the texture", the
look of his paper-craft boards; with photo textures or plain paper materials alone it read as a realistic 3D castle.

  B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
  nice -n 15 $B -b -t 2 -P blender/sets/palace/paperize_set.py -- --blend output/sets/palace-island.blend \
      --out output/sets/palace-island-folded --cams CAM_sea,CAM_texture [--width 0.06] [--angle 30] [--res 540x960]

Why other numbers than the characters': a character's ink line is 3.5 mm wide because it is seen from 1-3 m; a keep
seen from 50 m with a 35 mm lens has about 5 cm per pixel at 540 px, so the line is `width` 6 cm and the mottle is
coarser. The sea, the sky, the paper sun and the far mountain cards are left alone (their look is their own).
Lives in blender/sets/palace/ (outside the Episode 1 render stamp, which covers blender/*.py and blender/*/*.py).
"""
import os
import sys

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for d in ('blender', 'blender/world', 'blender/character', 'blender/sets'):
    p = os.path.join(REPO, d)
    if p not in sys.path:
        sys.path.insert(0, p)

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    k = '--' + name
    return ARGV[ARGV.index(k) + 1] if k in ARGV else default


BLEND = arg('blend')
OUT = arg('out')
CAMS = [c for c in (arg('cams') or '').split(',') if c]
WIDTH, ANGLE = float(arg('width', 0.06)), float(arg('angle', 30))
RES = arg('res', '540x960')
SAMPLES = int(arg('samples', 16))
CRAFT = '--craft' in ARGV
# --craft: every kit material becomes a SHEET of paper of its colour; without it only the fold lines and the paper
# surface are added. The code lives in blender/sets/paper_craft.py, the same pass build_set.py runs for a set whose
# JSON says "paper": "craft" (so a set built that way needs no paperize step at all).
import paper_craft  # noqa: E402

bpy.ops.wm.open_mainfile(filepath=os.path.abspath(BLEND))
sc = bpy.context.scene
paper_craft.apply(sc, {'look': 'craft', 'width': WIDTH, 'angle': ANGLE, 'sheets': CRAFT},
                  log=lambda m: print(m.replace('[paper craft]', '[paperize]')))
w, h = (int(v) for v in RES.split('x'))
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
if sc.render.engine == 'CYCLES':
    sc.cycles.samples = SAMPLES
else:
    try:
        sc.eevee.taa_render_samples = SAMPLES
    except AttributeError:
        pass
# the set's camera anchors are empties carrying lens_mm / fstop / focus_m; one real camera (KUROKO) is moved onto
# each of them, as blender/sets/build_set.py put_camera does
cam = bpy.data.objects.get('KUROKO') or next((o for o in sc.objects if o.type == 'CAMERA'), None)
sc.camera = cam
for i, name in enumerate(CAMS):
    a = bpy.data.objects.get(name)
    if a is None:
        print('[paperize] no camera anchor', name)
        continue
    cam.matrix_world = a.matrix_world.copy()
    cam.data.lens = a.get('lens_mm', cam.data.lens)
    cam.data.dof.use_dof = bool(a.get('fstop', 0) > 0)
    if cam.data.dof.use_dof:
        cam.data.dof.aperture_fstop, cam.data.dof.focus_distance = a['fstop'], a['focus_m']
    sc.render.filepath = os.path.abspath(OUT + ('' if i == 0 else '-' + name) + '.png')
    bpy.ops.render.render(write_still=True)
    print('[paperize] ->', sc.render.filepath)
