#!/usr/bin/env python3
"""MOVES GALLERY 2: every everyday move (film/src/everyday-moves.py -> library/moves.json) and the running gait
(engine/footlock.js, the run band) on one character, Musashi (recipe musashi-ai), on the Episode 1 beach.

    python3 film/src/everyday-moves.py && python3 film/src/moves-gallery-2.py      # -> film/moves-gallery-2.json
    node engine/validate.mjs film/moves-gallery-2.json
    node tools/footslide.mjs film/moves-gallery-2.json                              # 0 hops, no slide
    node tools/gait_check.mjs film/moves-gallery-2.json                             # the walk-up and the run
    node tools/timeline.mjs film/moves-gallery-2.json && python3 tools/motion_check.py moves-gallery-2
    bash tools/film.sh film/moves-gallery-2.json --set ganryujima-beach --res 270x480 --skip-audit --from F --to F

The film's `index` lists each move's start, end and the time of its review still (the moment that shows the move).
Kojiro is in the cast only because the engine wants two performers: hidden, far away.
"""
import json
import math
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'moves-gallery-2.json')
MOVES = json.load(open(os.path.join(os.path.dirname(OUT), '..', 'library', 'moves.json')))
FPS = 30
RY = round(math.pi / 2, 5)          # facing +x: the side cameras see him in profile
START = (-1.0, 0.0)

keys = [{'t': 0.0, 'pose': 'stand-easy', 'x': START[0], 'z': START[1], 'ry': RY},
        {'t': 0.6, 'pose': 'stand-easy'}]
index, cams = [], []
two_hand = []


def move_len(name):
    return max(b['dt'] for b in MOVES[name])


def at(t):
    return round(t, 3)


def play(t, name, still, cam=None, note=''):
    """The move at t; a key in the move's end pose 0.45 s after it ends keeps him standing (breathing) in between."""
    keys.append({'t': at(t), 'move': name})
    end = t + move_len(name)
    index.append({'move': name, 't': at(t), 'end': at(end), 'still': at(t + still), 'note': note})
    if cam:
        cams.append(dict(cam, t=at(t - 0.3)))
    return end


SIDE = {'rig': 'compose', 'subjects': ['hero'], 'basis': 'facing', 'az0': 86, 'az1': 94, 'elev': 4, 'size': 0.62,
        'screen': [0.5, 0.56], 'fov': 30, 'feel': 'dolly', 'cut': True}
THREEQ = dict(SIDE, az0=32, az1=40, note='three-quarter front')
LOW = dict(SIDE, elev=8, size=0.5, note='side, a little higher: the legs on the ground read')

t = 0.8
t = play(t, 'back-step', 0.45, dict(SIDE, note='back-step'), 'weight forward first, then 0.45 m back') + 0.6
t = play(t, 'sidestep-left', 0.45, dict(THREEQ, note='sidesteps'), 'lean away, slip 0.5 m left') + 0.5
t = play(t, 'sidestep-right', 0.45, None, 'and back') + 0.6
t = play(t, 'kneel-seiza', 1.75, dict(SIDE, note='seiza'), 'left foot back, left knee down, then sits on his heels') + 0.5
t = play(t, 'bow-seiza', 1.3, None, 'za-rei: the hands slide to the floor') + 0.5
t = play(t, 'rise-from-seiza', 0.95, None, 'up through a kneel') + 0.55
t = play(t, 'bow-standing', 1.2, dict(THREEQ, az0=60, az1=66, note='standing bow'), 'rei, 30 degrees') + 0.5
t = play(t, 'sit-down', 1.7, dict(LOW, note='sit'), 'seat behind the feet, knees up') + 0.7
t = play(t, 'stand-from-sit', 0.95, None, 'rock forward, squat, stand') + 0.55
t = play(t, 'look-around', 0.8, dict(THREEQ, az0=20, az1=24, size=0.5, note='look around'), 'head leads, chest follows') + 0.5
two_hand.append([at(t - 0.1), at(t + move_len('suriashi') + 0.3)])
t = play(t, 'suriashi', 0.55, dict(LOW, note='suriashi'), 'three sliding steps, the soles skim the sand') + 0.6
t = play(t, 'stumble-recover', 0.45, dict(SIDE, note='stumble'), 'the toe catches, catch steps, over-correct') + 0.55
t = play(t, 'fall-back', 0.75, dict(LOW, note='fall'), 'slip, arms up, lands on the seat') + 0.65
t = play(t, 'get-up', 1.1, None, 'rock forward, onto a knee, push up') + 0.6

# ---- THE RUN: a cut to the start of a straight 13 m run along the beach; he walks off, speeds up through the walk
# into the run (the gait changes band at about 2.2 m/s), runs at 3.6 m/s, slows to a stop
RUN0, VMAX = (-6.6, 0.0), 3.6
T_ACC, T_RUN, T_DEC = 1.8, 2.2, 1.5
t_run = at(t + 0.6)
keys.append({'t': at(t + 0.6 - 0.05), 'pose': 'stand-easy'})
keys.append({'t': t_run, 'pose': 'stand-easy', 'x': RUN0[0], 'z': RUN0[1], 'ry': RY, 'cut': True})
t0 = t_run + 0.5
keys.append({'t': at(t0), 'pose': 'stand-easy'})


def s_of(tt):
    """distance along the run at tt seconds after it starts: a smooth (cosine) speed-up, a cruise, a smooth stop"""
    if tt <= T_ACC:
        return VMAX * (tt / 2 - T_ACC / (2 * math.pi) * math.sin(math.pi * tt / T_ACC))
    d = VMAX * T_ACC / 2
    if tt <= T_ACC + T_RUN:
        return d + VMAX * (tt - T_ACC)
    d += VMAX * T_RUN
    u = min(tt - T_ACC - T_RUN, T_DEC)
    return d + VMAX * (u / 2 + T_DEC / (2 * math.pi) * math.sin(math.pi * u / T_DEC))


T_ALL = T_ACC + T_RUN + T_DEC
n = int(T_ALL / 0.2)
for i in range(1, n + 1):
    tt = T_ALL * i / n
    keys.append({'t': at(t0 + tt), 'pose': 'stand-easy', 'x': round(RUN0[0] + s_of(tt), 3), 'z': RUN0[1], 'ry': RY})
t_end_run = t0 + T_ALL
keys.append({'t': at(t_end_run + 0.5), 'pose': 'stand-easy', 'settle': 0.5})
index.append({'move': 'run', 't': at(t0), 'end': at(t_end_run), 'still': at(t0 + T_ACC + T_RUN / 2),
              'note': 'walk -> run at %.1f m/s over %.1f m -> stop' % (VMAX, s_of(T_ALL))})
cams.append(dict(SIDE, t=at(t_run), az0=88, az1=92, size=0.55, note='the run, tracked from the side'))
DUR = round(t_end_run + 1.3, 2)

film = {
    'title': 'Moves gallery 2: everyday moves and the run',
    'page': 'engine/motion.html', 'fps': FPS, 'width': 1080, 'height': 1920, 'format': 'vertical',
    'duration': DUR, 'mode': 'dawn',
    'motion': {'overlap': True, 'lockFeet': {'plantHolds': True}},
    'stage': {'mark': 'MARK_center', 'origin': True, 'turn': 0},
    'cast': {'hero': {'character': 'musashi', 'face': 'eyes', 'weapon': 'bokken', 'recipe': 'musashi-ai',
                      'weaponPart': 'bokken_oar_t1'},
             'target': {'character': 'kojiro', 'face': 'eyes', 'recipe': 'kojiro-ai2', 'hidden': True}},
    'performances': {
        'hero': {'keys': keys, 'twoHand': two_hand,
                 'gait': {'arms': [0.6, 1.0], 'note': 'the right hand carries the oar; both arms pump in the run'}},
        'target': {'keys': [{'t': 0.0, 'pose': 'neutral', 'x': 30.0, 'z': 30.0, 'ry': 0.0}]},
    },
    'index': index,
    'paperSurface': {'angle': 36.0, 'ink': 0.85, 'width': 0.003, 'light': 0.55, 'mottle': 0.12, 'mottle_scale': 7.0, 'ao': 0.35},
    'wind': {'to': [0.15, -1.0], 'strength': 3.2, 'gust': 0.6, 'seed': 2},
    'cameraOpts': {'solver': 2, 'aperture': 4.0},
    'effects': {'dof': 4.0, 'motionBlur': 0.5, 'vignette': 0.3, 'postFx': True},
    'fade': {'in': 0, 'out': 0.0},
    'camera': [dict(SIDE, t=0.0, cut=False, note='opening: side')] + cams,
    'sounds': [], 'titles': [],
}
json.dump(film, open(OUT, 'w'), indent=1)
print('->', OUT, '%d keys, %d moves, %.1f s' % (len(keys), len(index), DUR))
for r in index:
    print('  %-16s %6.2f-%6.2f still %6.2f  %s' % (r['move'], r['t'], r['end'], r['still'], r['note']))
