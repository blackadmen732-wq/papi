"""BUILD SET: compose a Paper Cinema set from a JSON file (library/sets/<name>.json) out of kit pieces
(blender/sets/kit.py), light it, add camera anchors and fighter marks, optionally put origami samurai on the marks,
save a .blend and render preview stills.

  B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
  nice -n 15 $B -b -t 2 -P blender/sets/build_set.py -- --set castle-courtyard --out output/sets/castle.blend \
      --preview output/sets/castle.png [--cams CAM_wide,CAM_medium] [--with-character hero:wide-stance,foe:hasso:demon]

Options:
  --set NAME|PATH        library/sets/NAME.json or a path              --out PATH   .blend to save (default output/sets/NAME.blend)
  --preview PATH         render stills (first cam -> PATH, others -> PATH-CAM_x.png)
  --cams A,B             camera anchors to render (default: the set's "preview_cams", else its first camera)
  --with-character LIST  role:pose[:demon][:trellis[=model]] separated by commas; role = mark name without MARK_ (hero, foe, ...);
                         :trellis = the rigged TRELLIS character (hero: ronin_base, others: samurai_front) instead of the box origami
                         :recipe=<id> = THE FILM CHARACTER (library/character-recipes/<id>.json, modular_builder), e.g. foe:hasso:recipe=kojiro
  --res WxH (540x960)    --samples N (set's render.samples or 32)    --quick (270x480, 12 samples)
  --seed N               override the set seed                       --exposure EV  override the grade
  --frame N              frame to render (particles and rain move)   --no-fog     skip fog pieces (fast look check)
  --no-post              skip the compositor (bloom, vignette)
  --paper craft|none     force the paper-craft look on / off (default: the set's "paper"; blender/sets/paper_craft.py)
  --polyhaven / --no-polyhaven   force the Poly Haven layer (CC0 photo textures + HDRI ambient) on / off for this
                         build, whatever the set's "polyhaven" says (before/after comparisons)

The JSON format (see docs/SETS.md): name, seed, lighting {preset, sky, sun, exposure, look, fighter, bloom,
vignette}, polyhaven (true | {textures, detail, hdri: role | {role, gain, clamp, sat, match, reflect, rot, mix} | false}),
materials {key: {overrides}}, pieces [{kit, name, pos, rot, scale, seed, params}], marks {MARK_x:
{pos, face}}, cameras {CAM_x: {pos, look | look_mark + look_z, lens, fstop, focus, note}}, preview_cams, render.
"""
import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
for p in (HERE, os.path.join(HERE, '..', 'world'), os.path.join(HERE, '..', 'character')):
    sys.path.insert(0, os.path.abspath(p))
import kit  # noqa: E402
import paper_craft  # noqa: E402
import paper_materials as pm  # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index('--' + n) + 1] if '--' + n in ARGV else d


def flag(n):
    return '--' + n in ARGV


# =========================================================================== lighting presets
PRESETS = {
    'night': dict(sky={'type': 'night', 'zenith': [0.003, 0.005, 0.014], 'horizon': [0.018, 0.024, 0.04], 'stars': 1.0, 'strength': 1.0},
                  sun={'elev': 38, 'az': 150, 'color': [0.62, 0.72, 1.0], 'energy': 0.35, 'angle': 1.5},
                  exposure=0.0, look='AgX - Medium High Contrast', bloom=0.7, vignette=0.4),
    'dusk': dict(sky={'type': 'nishita', 'strength': 0.6}, sun={'elev': 2.0, 'az': -60, 'color': [1.0, 0.48, 0.25], 'energy': 2.2, 'angle': 1.5},
                 exposure=-1.2, look='AgX - Medium High Contrast', bloom=0.5, vignette=0.35),
    'dawn': dict(sky={'type': 'nishita', 'strength': 1.0}, sun={'elev': 4.0, 'az': -7, 'color': [1.0, 0.62, 0.38], 'energy': 3.2, 'angle': 1.2},
                 exposure=-2.3, look='AgX - Medium High Contrast', bloom=0.4, vignette=0.3),
    'day': dict(sky={'type': 'nishita', 'strength': 1.0}, sun={'elev': 38, 'az': 135, 'color': [1.0, 0.94, 0.86], 'energy': 4.0, 'angle': 0.8},
                exposure=-3.3, look='AgX - Medium High Contrast', bloom=0.3, vignette=0.3),
    'overcast': dict(sky={'type': 'color', 'color': [0.55, 0.6, 0.65], 'strength': 0.8}, sun={'elev': 60, 'az': 0, 'color': [0.9, 0.93, 1.0], 'energy': 0.3, 'angle': 20},
                     exposure=-0.5, look='AgX - Base Contrast', bloom=0.2, vignette=0.3),
}
FIGHTER = {'key': {'offset': [-1.8, 2.4, 2.8], 'energy': 0.0, 'color': [1.0, 0.82, 0.62], 'size': 1.6},
           'fill': {'offset': [2.4, 1.6, 1.4], 'energy': 0.0, 'color': [0.7, 0.78, 1.0], 'size': 2.0},
           'rim': {'offset': [1.2, -2.6, 2.6], 'energy': 0.0, 'color': [0.62, 0.74, 1.0], 'size': 0.8}}


def merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def sun_dir(elev, az):
    el, a = math.radians(elev), math.radians(az)
    return Vector((math.sin(a) * math.cos(el), math.cos(a) * math.cos(el), math.sin(el)))


def build_sky(scene, sky, sun):
    world = bpy.data.worlds.new('SET_sky')
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    T = pm._NT(nt)
    bg = nt.nodes['Background']
    bg.inputs['Strength'].default_value = sky.get('strength', 1.0)
    kind = sky.get('type', 'nishita')
    if kind == 'nishita':
        pm.SKY.update(sun_elevation=math.radians(sun['elev']), sun_rotation=math.radians(sun['az']),
                      dust_density=sky.get('dust', 1.3), air_density=sky.get('air', 1.0))
        sk = pm.sky_node(T)
        nt.links.new(sk.outputs['Color'], bg.inputs['Color'])
    elif kind == 'night':
        tc = T.node('ShaderNodeTexCoord')
        z = T.node('ShaderNodeSeparateXYZ', Vector=tc.outputs['Generated']).outputs['Z']
        g = pm._smooth(T, z, -0.05, 0.55)
        col = T.mix_rgb(g, sky['horizon'], sky['zenith'])
        vo = pm._voronoi(T, tc.outputs['Generated'], 380.0)
        r = T.node('ShaderNodeSeparateColor', Color=vo.outputs['Color']).outputs[0]
        star = T.math('MULTIPLY', T.math('LESS_THAN', vo.outputs['Distance'], 0.06), T.math('GREATER_THAN', r, 0.55))
        star = T.math('MULTIPLY', star, T.math('MULTIPLY', T.math('POWER', r, 6.0), 0.8 * sky.get('stars', 1.0)))
        star = T.math('MULTIPLY', star, pm._smooth(T, z, 0.08, 0.35))
        col = T.mix_rgb(1.0, col, T.node('ShaderNodeCombineXYZ', X=star, Y=star, Z=T.math('MULTIPLY', star, 1.15)).outputs[0], blend='ADD')
        nt.links.new(col, bg.inputs['Color'])
    else:
        bg.inputs['Color'].default_value = (*sky.get('color', [0.5, 0.5, 0.5])[:3], 1)
    if sun.get('energy', 0) > 0:
        L = bpy.data.lights.new('SET_sun', 'SUN')
        L.energy = sun['energy']
        L.color = sun['color'][:3]
        L.angle = math.radians(sun.get('angle', 1.0))
        ob = bpy.data.objects.new('SET_sun', L)
        ob.rotation_euler = (-sun_dir(sun['elev'], sun['az'])).to_track_quat('-Z', 'Y').to_euler()
        return ob
    return None


# =========================================================================== Poly Haven HDRI ambient
PH_HDRI = {'night': 'night', 'dusk': 'dusk', 'dawn': 'dawn', 'day': 'day', 'overcast': 'overcast'}


def ph_config(S, preset):
    """The set's "polyhaven" block normalised to a dict (None = off). --polyhaven / --no-polyhaven override it."""
    v = S.get('polyhaven', False)
    if flag('no-polyhaven'):
        return None
    if flag('polyhaven') and not v:
        v = True
    if not v:
        return None
    cfg = dict(v) if isinstance(v, dict) else {}
    cfg.setdefault('textures', True)
    cfg.setdefault('detail', 1.0)
    cfg.setdefault('hdri', PH_HDRI.get(preset, 'night'))
    return cfg


def hdri_stats(img, clamp, step=2):
    """Mean radiance (solid-angle weighted, after clamping at clamp x mean) and the brightest spot's u of an
    equirectangular image."""
    import numpy as np
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[::step, ::step, :3]
    lum = px[..., 0] * 0.2126 + px[..., 1] * 0.7152 + px[..., 2] * 0.0722
    rows = lum.shape[0]
    lat = (np.arange(rows) + 0.5) / rows * math.pi - math.pi / 2         # row 0 = bottom
    wgt = np.cos(lat)[:, None]
    mean = float((lum * wgt).sum() / (wgt.sum() * lum.shape[1]))
    cap = clamp * mean
    for _ in range(3):                                                   # mean of the clamped image
        mean_c = float((np.minimum(lum, cap) * wgt).sum() / (wgt.sum() * lum.shape[1]))
        cap = clamp * mean_c
    iy, ix = np.unravel_index(int(np.argmax(lum)), lum.shape)
    k = np.minimum(1.0, cap / np.maximum(lum, 1e-9))[..., None]               # clamp the colour like the luminance
    rgb = tuple(float(v) for v in ((px * k) * wgt[..., None]).sum(axis=(0, 1)) / (wgt.sum() * lum.shape[1]))
    return mean_c, cap, (ix + 0.5) / lum.shape[1], (iy + 0.5) / rows, rgb


def sky_probe(world, clamp):
    """Mean radiance of the procedural world (clamped like the HDRI) from a tiny equirectangular render, so the HDRI
    can be normalised to the same overall ambient: the photo changes where light comes from and its colour, not the
    exposure the set was tuned for."""
    sc = bpy.data.scenes.new('_sky_probe')
    sc.world = world
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 8
    sc.cycles.use_denoising = False
    sc.render.threads_mode = 'FIXED'
    sc.render.threads = 2
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 128, 64, 100
    sc.render.image_settings.file_format = 'OPEN_EXR'
    sc.render.use_compositing = False
    cd = bpy.data.cameras.new('_sky_probe')
    cd.type = 'PANO'
    try:
        cd.panorama_type = 'EQUIRECTANGULAR'
    except Exception:
        cd.cycles.panorama_type = 'EQUIRECTANGULAR'
    cam = bpy.data.objects.new('_sky_probe', cd)
    sc.collection.objects.link(cam)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    sc.camera = cam
    path = os.path.join(REPO, 'output', 'sets', '_sky_probe.exr')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    img = bpy.data.images.load(path)
    mean, cap, _, _, rgb = hdri_stats(img, clamp, step=1)
    bpy.data.images.remove(img)
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(cd)
    bpy.data.scenes.remove(sc)
    return mean, rgb


def add_hdri(world, cfg, sun):
    """Light the set with a Poly Haven HDRI while the camera keeps seeing the procedural sky: diffuse and glossy
    rays see the HDRI (brightness normalised to `ambient`, the photographed sun clamped off so the set's sun or
    moon lamp keeps the only hard shadow, brightest spot turned to the set's sun azimuth), camera rays see the old
    world. Key / fill / rim and practical lights are untouched."""
    ent = cfg['hdri']
    if not ent:
        return None
    M = pm.PH['manifest'] or {}
    over = dict(ent) if isinstance(ent, dict) else {'role': ent}
    base = dict(M.get('hdris', {}).get(over.get('role'), {}))
    if not base:
        print('  ! polyhaven: no HDRI role', over.get('role'))
        return None
    base.update({k: v for k, v in over.items() if k != 'role'})
    files = pm.ph_files(base['id'])
    if not files or 'hdri' not in files:
        return None
    img = bpy.data.images.load(files['hdri'], check_existing=True)
    mean, cap, u, v, hrgb = hdri_stats(img, base.get('clamp', 8))
    ang_h = (u - 0.5) * 2 * math.pi
    a = math.radians(sun.get('az', 0))
    ang_s = math.atan2(math.cos(a), -math.sin(a))
    rot = ang_s - ang_h + math.radians(base.get('rot', 0))
    nt = world.node_tree
    T = pm._NT(nt)
    bg = nt.nodes['Background']
    wo = nt.nodes['World Output']
    tc = T.node('ShaderNodeTexCoord')
    mp = T.node('ShaderNodeMapping', Vector=tc.outputs['Generated'])
    mp.inputs['Rotation'].default_value = (0, 0, rot)
    env = T.node('ShaderNodeTexEnvironment', Vector=mp.outputs['Vector'])
    env.image = img
    cl = T.node('ShaderNodeVectorMath', Vector=env.outputs['Color'])
    cl.operation = 'MINIMUM'
    cl.inputs[1].default_value = (cap, cap, cap)
    hs = T.node('ShaderNodeHueSaturation', Color=cl.outputs['Vector'], Saturation=base.get('sat', 1.0))
    sky, srgb = sky_probe(world, base.get('clamp', 8))
    # colour match: pull the photo's overall colour toward the procedural sky's (the set's art-directed mood),
    # `match` 0 = the photo's own colour, 1 = the procedural sky's average colour; the photo's directional variation stays
    match = base.get('match', 0.7)
    lum3 = lambda c: max(1e-9, 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    gain3 = [((srgb[i] / lum3(srgb)) / max(1e-9, hrgb[i] / lum3(hrgb))) ** match for i in range(3)]
    gl = lum3(gain3)
    gain3 = [g / gl for g in gain3]
    cm = T.node('ShaderNodeVectorMath', Vector=hs.outputs['Color'])
    cm.operation = 'MULTIPLY'
    cm.inputs[1].default_value = gain3
    target = base['ambient'] if 'ambient' in base else base.get('gain', 1.0) * sky
    strength = target / max(mean, 1e-6)
    bg2 = T.node('ShaderNodeBackground', Color=cm.outputs['Vector'], Strength=strength)
    light = bg2.outputs['Background']
    mixw = base.get('mix', 1.0)
    if mixw < 1.0:
        mx0 = T.node('ShaderNodeMixShader', Fac=mixw)
        T.link(bg.outputs['Background'], mx0.inputs[1]); T.link(light, mx0.inputs[2])
        light = mx0.outputs['Shader']
    # camera rays (and part of the glossy rays: water and lacquer must still mirror the sky the camera sees) keep
    # the procedural world; `reflect` = how much of the HDRI the glossy rays see (default 0.25)
    lp = T.node('ShaderNodeLightPath')
    keep = T.math('MAXIMUM', lp.outputs['Is Camera Ray'], T.math('MULTIPLY', lp.outputs['Is Glossy Ray'], 1.0 - base.get('reflect', 0.25)))
    mx = T.node('ShaderNodeMixShader', Fac=keep)
    T.link(light, mx.inputs[1])
    T.link(bg.outputs['Background'], mx.inputs[2])
    T.link(mx.outputs['Shader'], wo.inputs['Surface'])
    print(f"  polyhaven HDRI {base['id']}: mean {mean:.4f}, procedural sky {sky:.4f} -> target {target:.4f} (x{strength:.2f}), "
          f"colour x({gain3[0]:.2f}, {gain3[1]:.2f}, {gain3[2]:.2f}), sun clamped at {cap:.3f}, hot spot u={u:.2f} v={v:.2f} turned {math.degrees(rot):.0f} deg to az {sun.get('az', 0)}")
    return base['id']


# =========================================================================== compositor
def _setp(node, name, value):
    if hasattr(node, name.lower().replace(' ', '_')):
        try:
            setattr(node, name.lower().replace(' ', '_'), value)
            return
        except Exception:
            pass
    if name in node.inputs:
        node.inputs[name].default_value = value


def post(scene, bloom, vignette):
    """Bloom (fog glow around lanterns, eyes, windows) and a soft vignette."""
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new('CompositorNodeRLayers')
    comp = nt.nodes.new('CompositorNodeComposite')
    sock = rl.outputs['Image']
    if bloom > 0:
        g = nt.nodes.new('CompositorNodeGlare')
        try:
            g.glare_type = 'BLOOM'
        except Exception:
            g.glare_type = 'FOG_GLOW'
        _setp(g, 'Quality', 'MEDIUM')
        _setp(g, 'Threshold', 0.8)
        _setp(g, 'Strength', bloom)
        _setp(g, 'Size', 0.6 if 'Size' in g.inputs else 8)
        if hasattr(g, 'mix'):
            g.mix = -1 + bloom
        nt.links.new(sock, g.inputs['Image'])
        sock = g.outputs['Image']
    if vignette > 0:
        em = nt.nodes.new('CompositorNodeEllipseMask')
        _setp(em, 'Width', 0.95)
        _setp(em, 'Height', 0.85)
        bl = nt.nodes.new('CompositorNodeBlur')
        _setp(bl, 'size_x', 160)
        _setp(bl, 'size_y', 160)
        if 'Size' in bl.inputs:
            try:
                bl.inputs['Size'].default_value = (160, 160)
            except Exception:
                pass
        nt.links.new(em.outputs['Mask'], bl.inputs['Image'])
        mr = nt.nodes.new('CompositorNodeMapRange')
        mr.inputs['From Min'].default_value = 0.0
        mr.inputs['From Max'].default_value = 1.0
        mr.inputs['To Min'].default_value = 1.0 - vignette
        mr.inputs['To Max'].default_value = 1.0
        nt.links.new(bl.outputs['Image'], mr.inputs['Value'])
        mx = nt.nodes.new('CompositorNodeMixRGB')
        mx.blend_type = 'MULTIPLY'
        nt.links.new(sock, mx.inputs[1])
        nt.links.new(mr.outputs['Value'], mx.inputs[2])
        sock = mx.outputs['Image']
    nt.links.new(sock, comp.inputs['Image'])


# =========================================================================== render settings
def setup_render(scene, R, res, samples):
    scene.render.engine = 'CYCLES'
    cy = scene.cycles
    cy.device = 'CPU'
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = R.get('adaptive', 0.04)
    cy.use_denoising = True
    cy.denoiser = 'OPENIMAGEDENOISE'
    cy.max_bounces = R.get('bounces', 6)
    cy.diffuse_bounces = R.get('diffuse_bounces', 3)
    cy.glossy_bounces = 3
    cy.transmission_bounces = 6
    cy.transparent_max_bounces = 8
    cy.volume_bounces = R.get('volume_bounces', 0)
    cy.volume_step_rate = R.get('volume_step_rate', 2.0)
    cy.volume_max_steps = 256
    cy.sample_clamp_indirect = R.get('clamp', 4.0)
    cy.use_light_tree = True
    cy.blur_glossy = 1.0
    scene.render.use_persistent_data = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 240
    scene.view_settings.view_transform = 'AgX'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False


# =========================================================================== marks, cameras
def make_marks(scene, coll, marks, clear_r):
    out = {}
    for name, m in marks.items():
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = 'ARROWS'
        e.empty_display_size = 0.8
        pos = Vector(m['pos'] + [0] * (3 - len(m['pos'])))
        e.location = pos
        if 'face' in m:
            d = Vector(m['face'][:2]) - pos.xy
            e.rotation_euler = (0, 0, math.atan2(d.y, d.x) - math.radians(90))
        elif 'yaw' in m:
            e.rotation_euler = (0, 0, math.radians(m['yaw']))
        e['role'] = m.get('role', '')
        coll.objects.link(e)
        out[name] = e
    return out


SKIP_SNAP = ('fog', 'mist', 'dust', 'emitter', 'rain', 'MOON', 'PI_', 'leaves', 'needles', 'blossom', 'crown')


def snap_marks(scene, marks, reach=2.5):
    """Put every mark on the surface below it (terrain, floor, sand), ignoring fog, particles and foliage. The
    search starts `reach` m above the mark, so roofs and ceilings over an interior mark are never hit."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for name, m in marks.items():
        p = m.location + Vector((0, 0, reach))
        for _ in range(12):
            hit, loc, nrm, idx, ob, mx = scene.ray_cast(dg, p, Vector((0, 0, -1)))
            if not hit:
                break
            if any(k in ob.name for k in SKIP_SNAP):
                p = loc - Vector((0, 0, 1e-4))
                continue
            if abs(loc.z - m.location.z) > 0.005:
                print(f'  mark {name}: snapped z {m.location.z:.2f} -> {loc.z:.2f} ({ob.name})')
            m.location.z = loc.z
            break


def make_cameras(scene, coll, cams, marks):
    anchors = {}
    for name, c in cams.items():
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = 'CONE'
        pos = Vector(c['pos'])
        if 'look_mark' in c:
            look = marks[c['look_mark']].location + Vector((0, 0, c.get('look_z', 1.2)))
        else:
            look = Vector(c['look'])
        e.location = pos
        e.rotation_euler = (look - pos).to_track_quat('-Z', 'Y').to_euler()
        if c.get('roll'):
            e.rotation_euler = (e.rotation_euler.to_matrix() @ __import__('mathutils').Matrix.Rotation(math.radians(c['roll']), 3, 'Z')).to_euler()
        e['lens_mm'] = c.get('lens', 35)
        e['look_at'] = list(look)
        e['fstop'] = c.get('fstop', 0)
        f = c.get('focus')
        if isinstance(f, str) and f in marks:
            e['focus_m'] = (marks[f].location + Vector((0, 0, 1.3)) - pos).length
        elif isinstance(f, (int, float)):
            e['focus_m'] = float(f)
        else:
            e['focus_m'] = (look - pos).length
        e['note'] = c.get('note', '')
        coll.objects.link(e)
        anchors[name] = e
    cd = bpy.data.cameras.new('KUROKO')
    cd.clip_start = 0.05
    cd.clip_end = 6000
    cd.sensor_fit = 'AUTO'
    cam = bpy.data.objects.new('KUROKO', cd)
    coll.objects.link(cam)
    scene.camera = cam
    return cam, anchors


def put_camera(cam, a):
    cam.matrix_world = a.matrix_world.copy()
    cam.data.lens = a['lens_mm']
    if a.get('fstop', 0) > 0:
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = a['fstop']
        cam.data.dof.focus_distance = a['focus_m']
    else:
        cam.data.dof.use_dof = False


# =========================================================================== characters
def add_characters(scene, coll, specs, marks, fighter):
    import origami_samurai as osam
    made = []
    for spec in specs:
        parts = spec.split(':')
        role, pose = parts[0], parts[1] if len(parts) > 1 else 'standing'
        demon = 'demon' in parts[2:]
        mk = marks.get('MARK_' + role)
        if mk is None:
            print(f'  ! no mark MARK_{role}; skipping character')
            continue
        yaw = mk.rotation_euler.z + math.pi
        ch = bpy.data.collections.new('CHAR_' + role)
        coll.children.link(ch)
        tre = next((x for x in parts[2:] if x.startswith('trellis')), None)
        rec = next((x for x in parts[2:] if x.startswith('recipe=')), None)
        if rec:
            # THE FILM CHARACTER: the modular paper character from a recipe (library/character-recipes/), in a
            # library/poses.json pose - exactly what blender/film_modular.py renders, so a set preview shows what a
            # film will show. role:pose:recipe=<id>, e.g. foe:hasso:recipe=kojiro. The origami stand-ins below stay
            # the default for set work that predates the recipes.
            sys.path.insert(0, os.path.join(REPO, 'blender', 'character'))
            import modular_builder as MB
            rp = os.path.join(REPO, 'library', 'character-recipes', rec.split('=', 1)[1] + '.json')
            res = MB.build(MB.load_recipe(rp), pose=pose, location=tuple(mk.location), yaw=yaw, collection=ch,
                           name='CHAR_' + role)
        elif tre:
            # the owner's TRELLIS character, rigged (blender/character/rig_trellis.py, docs/CHARACTER-BLENDER.md):
            # role:pose:trellis  (hero = ronin_base, any other role = samurai_front)  or  role:pose:trellis=<model>
            import rig_trellis as rtr
            model = tre.split('=')[1] if '=' in tre else ('ronin_base' if role == 'hero' else 'samurai_front')
            res = rtr.build_character(model, name='RIG_' + role, demonic=demon)
            rtr.apply_frame(res, rtr.pose_frame(pose if pose != 'standing' else 'chudan'))
            rtr.place(res, tuple(mk.location), yaw, collection=ch)
        else:
            res = osam.build(pose, tuple(mk.location), yaw, demon=demon, seed=3 + len(made), name='CHAR_' + role, collection=ch,
                             lamp_scale=fighter.get('lamp_scale', 0.12), seam_glow=fighter.get('seam_glow', 1.6),
                             eye_glow=fighter.get('eye_glow', 14.0), inner_glow=fighter.get('inner_glow', 1.5))
        M = mk.matrix_world
        aim = mk.location + Vector((0, 0, 1.25))
        for nm in ('key', 'fill', 'rim'):
            L = fighter[nm]
            if L.get('energy', 0) <= 0:
                continue
            ld = bpy.data.lights.new(f'LGT_{nm.capitalize()}_{role}', 'AREA')
            ld.energy = L['energy']
            ld.color = L['color'][:3]
            ld.size = L['size']
            lo = bpy.data.objects.new(ld.name, ld)
            lo.location = M @ Vector(L['offset'])
            lo.rotation_euler = (aim - lo.location).to_track_quat('-Z', 'Y').to_euler()
            ch.objects.link(lo)
        made.append(res)
        print(f'  character {role}: pose {pose}{" (demon)" if demon else ""} at {tuple(round(v, 2) for v in mk.location)}')
    return made


# =========================================================================== main
def main():
    t0 = time.time()
    name = arg('set', 'castle-courtyard')
    path = name if name.endswith('.json') else os.path.join(REPO, 'library', 'sets', name + '.json')
    S = json.load(open(path))
    set_name = S.get('name', os.path.splitext(os.path.basename(path))[0])
    seed = int(arg('seed', S.get('seed', 1)))
    R = S.get('render', {})
    quick = flag('quick')
    res = [int(v) for v in arg('res', '270x480' if quick else R.get('res', '540x960')).split('x')]
    samples = int(arg('samples', 12 if quick else R.get('samples', 32)))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = set_name
    colls = {}
    for c in ('SET', 'LIGHTS', 'MARKS', 'CAMERAS', 'CHARACTERS'):
        colls[c] = bpy.data.collections.new(c)
        scene.collection.children.link(colls[c])
    setup_render(scene, R, res, samples)

    Lg = S.get('lighting', {})
    Lg = merge(PRESETS.get(Lg.get('preset', 'night'), PRESETS['night']), Lg)
    phc = ph_config(S, S.get('lighting', {}).get('preset', 'night'))
    pm.ph_enable(bool(phc), scale=phc['detail'] if phc else 1.0)        # loads library/polyhaven.json
    sun = build_sky(scene, Lg['sky'], Lg['sun'])
    if phc:
        add_hdri(scene.world, phc, Lg['sun'])
    pm.PH['on'] = bool(phc and phc['textures'])                          # texture layer for every recipe built below
    scene['polyhaven'] = bool(phc)
    print('  polyhaven:', 'off' if not phc else f"textures {'on' if phc['textures'] else 'off'}, hdri {phc['hdri']}")
    if sun:
        colls['LIGHTS'].objects.link(sun)
    scene['set_sun'] = {'sun_elev': Lg['sun']['elev'], 'sun_az': Lg['sun']['az']}
    scene.view_settings.look = Lg.get('look', 'AgX - Medium High Contrast')
    scene.view_settings.exposure = float(arg('exposure', Lg.get('exposure', 0.0)))

    marks = make_marks(scene, colls['MARKS'], S.get('marks', {}), S.get('clear', 1.6))
    ctx = kit.Ctx(scene, colls['SET'], seed=seed, materials=S.get('materials', {}))
    ctx.clear = [(m.location.x, m.location.y, S.get('clear', 1.6)) for n, m in marks.items() if n in ('MARK_hero', 'MARK_foe', 'MARK_center')]
    ctx.fight = list(ctx.clear)   # the fighter marks only (ctx.clear later also holds the camera spots, some in the sea)
    ctx.clear += [(c['pos'][0], c['pos'][1], 0.8) for c in S.get('cameras', {}).values()]     # never grow a culm through a lens
    counts = {}
    _names = [sp.get('name', sp.get('kit')) for sp in S.get('pieces', []) + Lg.get('pieces', [])]
    _dupes = sorted({n for n in _names if _names.count(n) > 1})
    if _dupes:            # a second piece of the same name replaces the first one's material (pm.new_material): refuse
        raise SystemExit(f'set {S.get("name")}: piece names used twice (set pieces + lighting.pieces): {_dupes}')
    for spec in S.get('pieces', []) + Lg.get('pieces', []):
        if flag('no-fog') and spec['kit'] in ('fog',):
            continue
        tp = time.time()
        _before = set(bpy.data.objects)
        kit.build_piece(ctx, spec)
        for _ob in set(bpy.data.objects) - _before:     # which kit made it (the paper craft pass skips fog, cards...)
            _ob['pc_kit'] = spec['kit']
        counts[spec.get('name', spec['kit'])] = round(time.time() - tp, 2)
    if S.get('snap_marks', True):
        snap_marks(scene, marks, S.get('snap_reach', 2.5))
    for i, L in enumerate(Lg.get('lights', [])):
        kit.build_piece(ctx, {'kit': 'light', 'name': L.get('name', f'light_{i}'), 'pos': L['pos'], 'params': {k: v for k, v in L.items() if k not in ('pos', 'name')}})
    paper = S.get('paper')                              # "craft": the set becomes a paper model of itself
    if arg('paper'):
        paper = None if arg('paper') in ('none', 'off') else (paper if isinstance(paper, dict) else arg('paper'))
    if paper_craft.config(paper):
        tp = time.time()
        paper_craft.apply(scene, paper)
        print(f'  paper craft pass: {time.time() - tp:.1f}s')
    cam, anchors = make_cameras(scene, colls['CAMERAS'], S.get('cameras', {}), marks)
    fighter = merge(FIGHTER, Lg.get('fighter', {}))
    chars = arg('with-character')
    if chars:
        add_characters(scene, colls['CHARACTERS'], chars.split(','), marks, fighter)
    if not flag('no-post'):
        post(scene, Lg.get('bloom', 0.5), Lg.get('vignette', 0.3))
    frame = int(arg('frame', 1))
    scene.frame_set(frame)
    scene['paper_cinema_set'] = set_name
    scene['seed'] = seed
    cams = (arg('cams') or ','.join(S.get('preview_cams', [])) or next(iter(anchors), '')).split(',')
    if cams and cams[0] in anchors:
        put_camera(cam, anchors[cams[0]])
    nfaces = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
    print(f'BUILT {set_name} in {time.time() - t0:.1f}s: {len(bpy.data.objects)} objects, {nfaces} faces; slowest pieces:',
          sorted(counts.items(), key=lambda kv: -kv[1])[:4])

    out = os.path.abspath(arg('out', os.path.join(REPO, 'output', 'sets', set_name + '.blend')))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print('SAVED', out)

    prev = arg('preview')
    if prev:
        for i, cn in enumerate(cams):
            if cn not in anchors:
                print('  ! unknown camera', cn, '; known:', ', '.join(anchors))
                continue
            put_camera(cam, anchors[cn])
            base, ext = os.path.splitext(os.path.abspath(prev))
            scene.render.filepath = base + ('' if i == 0 else f'-{cn}') + (ext or '.png')
            os.makedirs(os.path.dirname(scene.render.filepath), exist_ok=True)
            t = time.time()
            bpy.ops.render.render(write_still=True)
            print(f'RENDERED {cn} -> {scene.render.filepath} in {time.time() - t:.1f}s ({res[0]}x{res[1]}, {samples} spp)')


if __name__ == '__main__':
    main()
