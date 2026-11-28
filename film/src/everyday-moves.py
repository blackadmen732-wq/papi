#!/usr/bin/env python3
"""EVERYDAY MOVES (28 Nov, Mark: "our character doesn't move properly: the leg movement, the whole articulation,
multiple different moves"). Writes the non-sword moves into the shared library, each as anticipation -> action ->
settle, and the poses they stand on:

    python3 film/src/everyday-moves.py        # -> library/poses.json, library/moves.json (idempotent: replaces its own)

The library stays the source of truth (a film calls {"t": 3, "move": "kneel-seiza"}); this file only keeps the numbers
in one readable place so they can be tuned and rewritten. The moves are built for "motion": {"lockFeet": {...,
"plantHolds": true}} (engine/footlock.js): the feet are planted where a pose HOLDS, so every root offset below is
chosen to keep the planted foot where it is (the hips travel over it) and only the foot that must move steps.

Conventions (docs/ANIMATION.md): fwd/side = metres along the facing / to the left at the move's start; y = root height
(sitting and kneeling go below 0: the crouch limit is 0.6); feetz = both feet ahead (+) / behind (-) the hips; slide 1 =
a sliding step. Positive hy / cy / ty turn to the figure's left; positive tx leans forward.
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TAG = 'everyday'          # every entry written here carries "_set": TAG, so a re-run replaces exactly these

# the right hand carries the oar / a blade low; the left arm hangs free
EASY = {'rsx': -0.2, 'rsz': 0.18, 'rex': -0.35, 'lsx': 0.02, 'lsz': -0.1, 'lex': -0.18, 'stance': 0.16, 'hx': 0.02}

POSES = {
    'stand-easy': dict(EASY),
    'bow-standing': {**EASY, 'tx': 0.5, 'cx': 0.12, 'hx': 0.12, 'nx': 0.06, 'rsx': -0.12, 'lsx': -0.2, 'lsz': -0.04,
                     'lex': -0.25, 'weight': -0.15, 'stance': 0.12},
    'kneel-one': {'stance': 0.45, 'crouch': 0.45, 'weight': 0.3, 'tx': 0.06, 'hx': 0.08, 'rsx': -0.3, 'rsz': 0.25,
                  'rex': -0.5, 'lsx': -0.55, 'lsz': -0.15, 'lex': -0.95},
    'kneel-push': {'stance': 0.45, 'crouch': 0.47, 'weight': 0.35, 'tx': 0.42, 'cx': 0.1, 'hx': -0.15, 'rsx': -0.45,
                   'rsz': 0.25, 'rex': -0.4, 'lsx': -0.75, 'lsz': -0.1, 'lex': -0.7},
    'seiza': {'stance': 0.0, 'feetz': -0.08, 'crouch': 0.55, 'tx': -0.02, 'hx': 0.06, 'rsx': -0.5, 'rsz': 0.12,
              'rex': -0.95, 'lsx': -0.5, 'lsz': -0.12, 'lex': -0.95},
    'bow-seiza': {'stance': 0.0, 'feetz': -0.08, 'crouch': 0.55, 'weight': 0.0, 'tx': 0.75, 'cx': 0.3, 'hx': 0.2,
                  'nx': 0.1, 'rsx': -1.0, 'rsz': 0.12, 'rex': -0.35, 'lsx': -1.0, 'lsz': -0.12, 'lex': -0.35},
    'sit-ground': {'stance': 0.12, 'feetz': 0.4, 'crouch': 0.6, 'tx': 0.18, 'hx': 0.1, 'rsx': -1.0, 'rsz': 0.2,
                   'rex': -0.65, 'lsx': -1.05, 'lsz': -0.15, 'lex': -0.6},
    'fall-sit': {'stance': 0.2, 'feetz': 0.45, 'crouch': 0.6, 'tx': -0.35, 'cx': -0.12, 'hx': 0.3, 'nx': 0.1,
                 'rsx': 0.6, 'rsz': 0.4, 'rex': -0.1, 'lsx': 0.6, 'lsz': -0.4, 'lex': -0.1},
    'squat-rise': {'stance': 0.2, 'feetz': 0.05, 'crouch': 0.5, 'tx': 0.55, 'cx': 0.15, 'hx': -0.2, 'rsx': -0.9,
                   'rsz': 0.2, 'rex': -0.5, 'lsx': -1.0, 'lsz': -0.15, 'lex': -0.4},
    'stumble-pitch': {'stance': 0.55, 'crouch': 0.18, 'weight': 0.6, 'tx': 0.55, 'cx': 0.2, 'hx': -0.35, 'nx': -0.15,
                      'rsx': -1.3, 'rsz': 0.6, 'rex': -0.5, 'lsx': -1.5, 'lsz': -0.7, 'lex': -0.4},
    'flail-back': {'stance': 0.3, 'crouch': 0.12, 'weight': -0.7, 'tx': -0.3, 'cx': -0.15, 'hx': 0.3, 'rsx': -1.6,
                   'rsz': 0.7, 'rex': -0.6, 'lsx': -1.8, 'lsz': -0.8, 'lex': -0.5},
    'look-left': {**EASY, 'ty': 0.1, 'cy': 0.18, 'ny': 0.2, 'hy': 0.5, 'hx': 0.0},
    'look-right': {**EASY, 'ty': -0.1, 'cy': -0.18, 'ny': -0.2, 'hy': -0.5, 'hx': 0.0},
    'suriashi-kamae': {'stance': 0.4, 'crouch': 0.1, 'weight': 0.1, 'tx': 0.03, 'hx': -0.02, 'rsx': -0.75, 'rsz': 0.1,
                       'rex': -0.85, 'lsx': -0.8, 'lsz': -0.1, 'lex': -0.95, 'slide': 1.0},
}

Y_SEIZA, Y_SIT, Y_FALL = -0.03, -0.2, -0.22

MOVES = {
    # STEP BACK: the weight comes forward onto the front foot first (anticipation), the body pushes back 0.45 m, the
    # chest a beat behind the hips, and settles
    'back-step': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.2, 'pose': 'stand-easy', 'weight': 0.3, 'tx': 0.06, 'crouch': 0.03, 'ease': 'antic'},
        {'dt': 0.58, 'pose': 'stand-easy', 'fwd': -0.45, 'weight': -0.35, 'tx': -0.05, 'hx': 0.08, 'crouch': 0.05,
         'stance': 0.28, 'ease': 'out'},
        {'dt': 1.0, 'pose': 'stand-easy', 'fwd': -0.45, 'settle': 0.6},
    ],
    # SIDESTEP: lean away and load (anticipation), slip 0.5 m to the side, settle
    'sidestep-left': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.2, 'pose': 'stand-easy', 'tz': -0.06, 'crouch': 0.04, 'hy': 0.1, 'ease': 'antic'},
        {'dt': 0.58, 'pose': 'stand-easy', 'side': 0.5, 'tz': 0.05, 'crouch': 0.05, 'hy': 0.05, 'ease': 'out'},
        {'dt': 1.0, 'pose': 'stand-easy', 'side': 0.5, 'settle': 0.6},
    ],
    'sidestep-right': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.2, 'pose': 'stand-easy', 'tz': 0.06, 'crouch': 0.04, 'hy': -0.1, 'ease': 'antic'},
        {'dt': 0.58, 'pose': 'stand-easy', 'side': -0.5, 'tz': -0.05, 'crouch': 0.05, 'hy': -0.05, 'ease': 'out'},
        {'dt': 1.0, 'pose': 'stand-easy', 'side': -0.5, 'settle': 0.6},
    ],
    # KNEEL TO SEIZA: draw up and look down (anticipation), the left foot steps back and the left knee goes down
    # (kneel-one: the right foot stays planted, so the hips move back 0.145 m), then the right foot slides back
    # beside it and he sits on his heels (the left foot stays: the hips go back to 0.29 m), and settles
    'kneel-seiza': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.28, 'pose': 'stand-easy', 'crouch': -0.01, 'hx': 0.16, 'ease': 'antic'},
        {'dt': 0.85, 'pose': 'kneel-one', 'fwd': -0.145},
        {'dt': 1.05, 'pose': 'kneel-one', 'fwd': -0.145, 'hx': 0.1},
        {'dt': 1.45, 'pose': 'seiza', 'fwd': -0.29, 'y': Y_SEIZA, 'ease': 'out'},
        {'dt': 1.85, 'pose': 'seiza', 'fwd': -0.29, 'y': Y_SEIZA, 'settle': 0.5},
        {'dt': 2.3, 'pose': 'seiza', 'fwd': -0.29, 'y': Y_SEIZA},
    ],
    # RISE FROM SEIZA: lean forward and gather (anticipation), the right foot steps forward to a kneel (the left knee
    # stays: the hips come forward 0.145 m), push up off it to standing (the right foot stays), settle
    'rise-from-seiza': [
        {'dt': 0, 'pose': 'seiza', 'y': Y_SEIZA},
        {'dt': 0.3, 'pose': 'seiza', 'y': Y_SEIZA, 'tx': 0.14, 'hx': 0.02, 'ease': 'antic'},
        {'dt': 0.85, 'pose': 'kneel-push', 'fwd': 0.145},
        {'dt': 1.05, 'pose': 'kneel-push', 'fwd': 0.145, 'tx': 0.46},
        {'dt': 1.65, 'pose': 'stand-easy', 'fwd': 0.29, 'tx': 0.06, 'ease': 'out'},
        {'dt': 2.15, 'pose': 'stand-easy', 'fwd': 0.29, 'settle': 0.5},
    ],
    # SIT DOWN on the ground: a little dip and a glance down (anticipation), the hips go back and down while the
    # arms reach forward for balance, the seat lands behind the feet (the feet stay planted: the hips go back 0.4 m),
    # settle into the sit
    'sit-down': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.3, 'pose': 'stand-easy', 'crouch': 0.05, 'tx': 0.1, 'hx': 0.12, 'ease': 'antic'},
        {'dt': 1.0, 'pose': 'squat-rise', 'fwd': -0.05, 'feetz': 0.05, 'weight': -0.3, 'y': -0.04},
        {'dt': 1.5, 'pose': 'sit-ground', 'fwd': -0.4, 'y': Y_SIT, 'ease': 'out'},
        {'dt': 2.0, 'pose': 'sit-ground', 'fwd': -0.4, 'y': Y_SIT, 'settle': 0.5},
    ],
    # STAND FROM A SIT: rock forward (anticipation), the hips come forward over the feet into a squat, stand, settle
    'stand-from-sit': [
        {'dt': 0, 'pose': 'sit-ground', 'y': Y_SIT},
        {'dt': 0.35, 'pose': 'sit-ground', 'y': Y_SIT, 'tx': 0.4, 'ease': 'antic'},
        {'dt': 0.95, 'pose': 'squat-rise', 'fwd': 0.35, 'y': -0.04},
        {'dt': 1.55, 'pose': 'stand-easy', 'fwd': 0.4, 'tx': 0.05, 'ease': 'out'},
        {'dt': 2.05, 'pose': 'stand-easy', 'fwd': 0.4, 'settle': 0.5},
    ],
    # STANDING BOW (rei): draw up (anticipation), bow 30 degrees from the hips in 0.7 s, hold, rise slower, settle
    'bow-standing': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.25, 'pose': 'stand-easy', 'tx': -0.03, 'hx': -0.05, 'crouch': -0.01, 'ease': 'antic'},
        {'dt': 0.95, 'pose': 'bow-standing', 'ease': 'out'},
        {'dt': 1.5, 'pose': 'bow-standing', 'tx': 0.53},
        {'dt': 2.35, 'pose': 'stand-easy', 'ease': 'in'},
        {'dt': 2.7, 'pose': 'stand-easy', 'settle': 0.4},
    ],
    # KNEELING BOW (za-rei, from seiza): straighten (anticipation), the hands slide forward to the floor as the body
    # folds, hold, come back up, settle
    'bow-seiza': [
        {'dt': 0, 'pose': 'seiza', 'y': Y_SEIZA},
        {'dt': 0.3, 'pose': 'seiza', 'y': Y_SEIZA, 'tx': -0.06, 'hx': -0.05, 'ease': 'antic'},
        {'dt': 1.05, 'pose': 'bow-seiza', 'y': Y_SEIZA, 'ease': 'out'},
        {'dt': 1.7, 'pose': 'bow-seiza', 'y': Y_SEIZA, 'tx': 0.78},
        {'dt': 2.55, 'pose': 'seiza', 'y': Y_SEIZA, 'ease': 'in'},
        {'dt': 2.9, 'pose': 'seiza', 'y': Y_SEIZA, 'settle': 0.4},
    ],
    # STUMBLE AND RECOVER: the toe catches (the body keeps going, the hips lag: the anticipation is the trip), he
    # pitches forward with the arms flung out and catches himself with quick steps, over-corrects back, settles
    'stumble-recover': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.18, 'pose': 'stand-easy', 'fwd': 0.12, 'tx': 0.22, 'hx': -0.1, 'weight': 0.4, 'ease': 'antic'},
        {'dt': 0.45, 'pose': 'stumble-pitch', 'fwd': 0.6, 'drag': 0},
        {'dt': 0.8, 'pose': 'stumble-pitch', 'fwd': 0.95, 'tx': 0.32, 'crouch': 0.14, 'weight': 0.3},
        {'dt': 1.2, 'pose': 'stand-easy', 'fwd': 1.1, 'tx': -0.07, 'hx': 0.06, 'ease': 'out'},
        {'dt': 1.65, 'pose': 'stand-easy', 'fwd': 1.1, 'settle': 0.8},
    ],
    # FALL (backwards, onto the seat): the foot slips and the arms fly up (anticipation), he drops, lands sitting with
    # the hands behind him (the feet stay where they were: the seat lands 0.45 m behind them), a small bounce, settle
    'fall-back': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.22, 'pose': 'flail-back', 'fwd': -0.05, 'ease': 'antic'},
        {'dt': 0.5, 'pose': 'squat-rise', 'fwd': -0.22, 'feetz': 0.22, 'tx': -0.1, 'weight': -0.5, 'y': -0.06, 'ease': 'in'},
        {'dt': 0.68, 'pose': 'fall-sit', 'fwd': -0.45, 'y': Y_FALL, 'drag': 0, 'ease': 'in'},
        {'dt': 0.85, 'pose': 'fall-sit', 'fwd': -0.45, 'y': Y_FALL + 0.02, 'tx': -0.42},
        {'dt': 1.35, 'pose': 'fall-sit', 'fwd': -0.45, 'y': Y_FALL, 'settle': 0.6},
    ],
    # GET UP (from the fall): rock forward and bring the arms round (anticipation), roll onto one knee (the right foot
    # stays planted), push up off the knee, stand, settle
    'get-up': [
        {'dt': 0, 'pose': 'fall-sit', 'y': Y_FALL},
        {'dt': 0.4, 'pose': 'sit-ground', 'y': Y_SIT, 'tx': 0.32, 'feetz': 0.45, 'ease': 'antic'},
        {'dt': 1.0, 'pose': 'kneel-push', 'fwd': 0.325},
        {'dt': 1.2, 'pose': 'kneel-push', 'fwd': 0.325, 'tx': 0.46},
        {'dt': 1.8, 'pose': 'stand-easy', 'fwd': 0.47, 'crouch': 0.12, 'tx': 0.2, 'ease': 'out'},
        {'dt': 2.2, 'pose': 'stand-easy', 'fwd': 0.47, 'settle': 0.5},
    ],
    # LOOK AROUND: a small counter-turn (anticipation), the head leads and the chest follows to the left, hold,
    # across to the right, hold, back to the front, settle
    'look-around': [
        {'dt': 0, 'pose': 'stand-easy'},
        {'dt': 0.25, 'pose': 'stand-easy', 'hy': -0.08, 'hx': 0.04, 'ease': 'antic'},
        {'dt': 0.8, 'pose': 'look-left', 'ease': 'out'},
        {'dt': 1.4, 'pose': 'look-left', 'hy': 0.55},
        {'dt': 2.1, 'pose': 'look-right'},
        {'dt': 2.7, 'pose': 'look-right', 'hy': -0.55},
        {'dt': 3.2, 'pose': 'stand-easy', 'ease': 'out'},
        {'dt': 3.6, 'pose': 'stand-easy', 'settle': 0.4},
    ],
    # SURIASHI (the fighter's sliding walk, okuri-ashi): sink into the stance (anticipation), three sliding steps of
    # 0.4 m, each the front foot first and the back foot drawn after it, the soles skimming the floor (slide 1), settle
    'suriashi': [
        {'dt': 0, 'pose': 'suriashi-kamae', 'crouch': 0.04},
        {'dt': 0.3, 'pose': 'suriashi-kamae', 'crouch': 0.12, 'ease': 'antic'},
        {'dt': 0.68, 'pose': 'suriashi-kamae', 'fwd': 0.4},
        {'dt': 0.9, 'pose': 'suriashi-kamae', 'fwd': 0.4},
        {'dt': 1.28, 'pose': 'suriashi-kamae', 'fwd': 0.8},
        {'dt': 1.5, 'pose': 'suriashi-kamae', 'fwd': 0.8},
        {'dt': 1.88, 'pose': 'suriashi-kamae', 'fwd': 1.2, 'ease': 'out'},
        {'dt': 2.3, 'pose': 'suriashi-kamae', 'fwd': 1.2, 'settle': 0.5},
    ],
}


def write(path, add, about_key='_about'):
    d = json.load(open(path))
    for k in [k for k, v in d.items() if isinstance(v, (dict, list)) and k in add]:
        del d[k]
    d.update(add)
    s = json.dumps(d, indent=1, ensure_ascii=False)
    open(path, 'w').write(s)
    return len(add)


if __name__ == '__main__':
    n1 = write(os.path.join(REPO, 'library', 'poses.json'), POSES)
    n2 = write(os.path.join(REPO, 'library', 'moves.json'), MOVES)
    print('everyday: %d poses -> library/poses.json, %d moves -> library/moves.json' % (n1, n2))
