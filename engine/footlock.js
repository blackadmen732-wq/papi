// FOOT LOCK + WEIGHT (opt-in: film "motion": { "lockFeet": true })
//
// The problem it fixes: every pose is a joint angle, so the legs are drawn from the hips down and the
// feet go wherever the hips take them. A travelling body therefore skates: the audit (tools/audit.mjs,
// rule A1) sees a "planted" foot slide metres across the ground.
//
// What this does, in one precomputed pass over the whole performance:
//   1. SAMPLE the finished motion (after the anime layer) at `rate` Hz: root x/y/z, facing, stance,
//      crouch, weight, stride/phase — and from those the *nominal* world position of each foot, i.e.
//      exactly where engine/figure.js solveLegs would put it today.
//   2. CONTACTS. A foot is in the air when the root is off the ground (a jump) or when the body is
//      travelling faster than a foot can push (`runSpeed`): that is a lunge or a leap, not a step.
//      Everything else is ground time, and ground time is cut into CONTACTS: the longest run of frames
//      whose nominal foot positions all sit within `tol` of one point. That one point is the plant —
//      the mean of the nominal path, so the body passes *over* the foot instead of the foot chasing
//      the body (that is also how a sprint is caught: you plant ahead and rotate over it).
//   3. STEPS. Between two contacts the foot swings for `swing` seconds: lift, travel, plant, on a
//      smoothstep with a sine arc. The two feet are staggered so they do not leave the ground together
//      at walking speed.
//   4. WEIGHT. With the feet pinned, the hips are no longer free:
//      · reach — if a pinned foot is further from its hip than the leg is long, the hips must DROP
//        (`crouch`) until the leg reaches. A long stride therefore sinks the body by itself.
//      · support polygon — the span between the planted feet (plus the soles). When the centre of
//        mass leaves it the body is falling: it leans the way it is falling (`rx`/`rz`, a rotation
//        about the ground, i.e. about the feet), the hips drop further, and the next plant is thrown
//        `lead` ahead along the travel direction to catch it.
//
// Everything is a pure function of t: the plan is built once from a uniform grid, and evaluation only
// looks it up, so any frame still renders on its own (window.renderAt(t)) and stills match the video.
import { LEG } from './figure.js';

export const FOOTLOCK = {
  rate: 120,         // planning grid (Hz)
  reach: 0.38,       // how far the body may travel either side of a plant before the foot must step (m):
                     //   half a stride. The body passes over the planted foot; the hips drop to reach it.
  swing: 0.15,       // how long a step takes (s)
  lift: 0.12,        // peak foot lift in a step (m), scaled by step length
  runSpeed: 5.5,     // above this ground speed the feet are off the ground (a lunge / leap), m/s
  air: 0.03,         // root height that counts as airborne (m)
  flight: 0.2,       // how high the feet come off the ground in a lunge / leap (m)
  ramp: 0.07,        // push-off / reach-down time at the two ends of a flight (s)
  lead: 0.08,        // catch step: throw the plant this many seconds of travel ahead
  lean: 0.55,        // falling lean per metre of centre-of-mass overhang (rad/m)
  drop: 0.3,         // hip drop per metre of overhang (m/m)
  maxLean: 0.22, maxDrop: 0.3,
  smooth: 0.08,      // smoothing window for the hip/lean pass (s)
  gap: 0.04,         // a walk alternates: a foot does not lift within this long of the other foot's step (s)
  minContact: 0.12,  // ...but a plant lasts at least this long (s)
  sole: [0.055, 0.11],   // half width / half length of a sole: the support polygon of one foot (m)
  dilate: 1,         // the hips' drop is dilated over this share of the smoothing window before it is averaged
  hipAccel: 1.5,     // walking: the hips' largest vertical acceleration (m/s^2) as they dip for the legs to reach
  // GAIT v2 (28 Nov). Measured on Episode 1 (tools/gait_check.mjs) the walks were a shuffle: every step swung in 0.15 s
  // (a human swing takes 0.33-0.48 s), both feet were down 60-76% of the time (human 16-28%), 157 steps a minute at
  // 1.24 m/s (human 100-125), the hips bobbed 11 cm (human 2.5-6) and the feet never rolled. While the body WALKS (a
  // sustained travel, not a lunge) the planner now walks like a person; everything else keeps the fighter's footwork.
  walkFrom: 0.25, walkFull: 0.6,   // sustained ground speed (m/s) where the walking gait starts / is full
  walkHold: 0.25,    // "sustained": the slowest speed within this many seconds either side (a 0.3 s lunge is no walk)
  walkBlend: 0.2,    // the walking amount fades over this long (s)
  swingK: 0.55,      // walking swing time = swingK / speed (s), clamped to [swing, swingMax]: 0.44 s at 1.25 m/s (the
                     //   toe still brushes the ground for a moment after it and the heel touches just before the strike)
  swingMax: 0.5,
  reachWalk: [0.18, 0.15, 0.28, 0.44],   // walking reach (half a stride) = a + b * speed, clamped to [lo, hi] (m)
  walkLift: 0.03,    // the hips ride this much higher while walking (m): the rig stands with its knees bent 34 deg
  walkSoft: 0.98,    // ... and the leg solve is firmer (figure.js soft IK from 0.94 of the reach): a stance knee near 15 deg
  heelStrike: 0.26,  // the toe is up this much as the heel lands (rad, 15 deg) ...
  loading: 0.1,      // ... and the sole slaps flat over this long (s)
  toeOff: 0.5,       // the heel is up this much as the toe leaves (rad, 29 deg; a rigid sandal pivots on its toe) ...
  heelOff: 0.4,      // ... rising over this share of the stance (at most 0.3 s)
  swingRise: 0.03,   // walking swing: the ankle rises this much above its toe-off height early in the swing (m) ...
  swingMid: 0.012,   // ... and passes this much above its heel-strike height at mid-swing (the toe ~3 cm up)
  hipSway: 0.022,    // the body over the standing foot (m either side)
  hipYaw: 0.06,      // the waist turns with the forward leg (rad either side) ...
  chestCounter: 1.7, // ... and the chest turns back by this many times that (the shoulders against the hips)
  armSwing: 0.32,    // shoulder swing (rad either side) of an arm whose performances.<id>.gait.arms amount is 1
  // TURNING (28 Nov): a planted foot keeps its own direction on the ground and the body twists over it (up to
  // footTwist); once the body has turned turnStep from where the foot was planted, the foot steps round to a new plant.
  // Before, a planted foot turned with the body: a turn on the spot spun both feet 180 deg on the sand.
  turnStep: 0.87,    // rad (50 deg)
  footTwist: 1.05,   // rad (60 deg): the most a planted foot is turned against the body
  // RUNNING (28 Nov, a speed band above the walk). A sustained speed from runFrom (full at runFull) is a run: each foot
  // is on the ground only for the contact time and the two contacts never overlap, so between two steps BOTH feet are
  // off the ground (the flight phase); the strides are long, the swinging heel comes up behind, the hips sink at
  // mid-stance and ride high in the flight, the body leans into the speed and the free arms pump with bent elbows.
  // Below runFrom nothing here runs: the walk is the walk above, unchanged. Ranges: tools/gait_check.mjs RUN_REF.
  runFrom: 2.0, runFull: 2.6,      // sustained ground speed (m/s): the run starts / is full
  runCadence: [140, 9, 150, 190],  // steps per minute = a + b * speed, clamped [lo, hi]: 167 at 3 m/s, 176 at 4
  runContact: [0.12, 0.45],        // ground contact per step (s) = a + b / speed: 0.27 s at 3 m/s, 0.23 at 4
  runLift: [0.1, 0.07, 0.2, 0.42], // the swinging ankle's peak over the line between its plants = a + b * speed (m)
  runReachDrop: false,   // (tried 28 Nov: the hips also come down to a swinging foot reaching for its plant. Worse:
                         //  pelvis bob 9 -> 10.5 cm, stance knee 52 -> 57 deg)
  runPlant: -0.02,     // a running foot is planted this many seconds of travel behind the middle of its contact
  runBob: 0.045,     // the hips sink this much at mid-stance below their flight height (m) ...
  runSink: 0.0,      // ... around this extra crouch (m)
  runStrike: 0.12,   // a running foot lands nearly flat (rad toe up; a sandal runner lands on the midfoot) ...
  runLoading: 0.04,  // ... slaps down over this long (s) ...
  runToeOff: 0.8,    // ... and pushes off this far heel up (rad, 46 deg; measured toe-off pitch -43) ...
  runHeelOff: 0.55,  // ... the heel rising over this share of the contact
  runLean: [0.06, 0.035, 0.24],    // torso lean forward = a + b * speed, at most c (rad): 0.17 rad at 3 m/s
  runArm: 0.6,       // shoulder pump (rad either side) of an arm whose gait.arms amount is 1 ...
  runElbow: -1.45,   // ... the elbow bent to about 85 deg ...
  runArmFwd: -0.12,  // ... the swing centred a little forward
  runSway: 0.008,    // hips over the standing foot while running (m either side): a runner's feet land near one line
  runYaw: 0.1,       // the waist turns with the forward leg (rad either side)
  // PLANT ON HOLDS (opt-in, film/moves-gallery-2.json): outside a walk, a foot is planted where the pose HOLDS (the
  // mean weighted by stillness), and once a contact holds a still pose the foot steps as soon as the pose moves it
  // holdTol away. Off (the default), a contact is planted at the plain mean of its path: a 0.45 m step back between two
  // holds never stepped (both holds were within `reach` of the middle) and both feet stood half way, off both poses.
  plantHolds: false,
  holdTol: 0.05,     // m
  holdSpeed: 0.05,   // the nominal foot moving slower than this (m/s) is holding
  slideLift: 0.012,  // a sliding step (pose channel `slide` 1: suriashi) lifts the foot this much (m)
};

// the sandal under the ankle (engine/figure.js: the zori runs from 6.5 cm behind the ankle to 18.5 cm in front of it,
// its underside 5.1 cm below): the points a walking foot pivots on, as [forward, up] from the ankle
const HEEL = [-0.065, -0.051], TOE = [0.185, -0.051];

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const ss = (u) => u * u * (3 - 2 * u);
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));   // an angle into (-pi, pi]

/** The ankle of a foot turned `th` (+ toe up) about its heel (pv -1) or toe (pv 1), from the flat ankle `a` (world),
 *  the foot facing `ry`. */
function pivotAnkle(a, ry, th, pv) {
  if (!th || !pv) return [a[0], a[1], a[2]];
  const [pz, py] = pv < 0 ? HEEL : TOE, c = Math.cos(th), s = Math.sin(th);
  const oz = pz + (-pz * c + py * s), oy = py + (-pz * s - py * c);    // ankle - pivot, turned, plus the pivot
  return [a[0] + Math.sin(ry) * oz, a[1] + oy, a[2] + Math.cos(ry) * oz];
}

/** Where solveLegs would put a foot today, in the world. side: -1 right (leads), +1 left. */
function nominal(p, side) {
  const front = side < 0;
  let lz = (front ? 1 : -1) * p.stance / 2 + (p.feetz ?? 0), ly = LEG.footY;
  if (p.stride > 0) {
    const ph = p.phase + (front ? 0 : Math.PI);
    lz += Math.sin(ph) * p.stride / 2;
    ly += Math.max(0, Math.cos(ph)) * 0.07;
  }
  const lx = side * 0.1, c = Math.cos(p.ry), s = Math.sin(p.ry);
  return [p.x + lx * c + lz * s, p.y + ly, p.z - lx * s + lz * c];
}

/**
 * Wrap a motion (t) => pose so the feet are planted in the world and the body carries its weight.
 * @param motion  the finished motion function, e.g. from makeMotion()
 * @param dur     film duration (s)
 * @param opts    true, or overrides of FOOTLOCK
 * @returns (t) => pose, with `_feet` = { r: [x,y,z], l: [x,y,z], rc, lc } (rc/lc = 1 while planted)
 */
export function lockFeet(motion, dur, opts = {}, gait = null) {
  const O = { ...FOOTLOCK, ...(opts === true ? {} : opts) };
  // per performer (film.performances.<id>.gait): arms = how much each arm [right, left] swings while walking (0 = it
  // holds something: a hand on the hilt never swings; default 0, so a film opts in)
  const GA = (gait && Array.isArray(gait.arms)) ? gait.arms : [0, 0];
  const RATE = O.rate, DT = 1 / RATE, N = Math.max(2, Math.ceil(dur * RATE) + 1);
  const P = [];                                       // the sampled performance
  for (let i = 0; i < N; i++) P.push(motion(i * DT));
  // CUTS (makeMotion's teleports, motion.cuts): each sample's piece of continuity. No speed, contact, step or smoothing
  // reaches across one: the feet jump with the body (27 Nov, Episode 1: after the cut Musashi's feet stayed at the
  // boat and flew 2.5 m to his body over 5 frames, a "step" planned across the teleport)
  const cuts = motion.cuts || [];
  const piece = P.map((_, i) => cuts.reduce((k, [, b]) => k + (i * DT >= b - 1e-6 ? 1 : 0), 0));
  const nb = (i, d) => { const k = clamp(i + d, 0, N - 1); return piece[k] === piece[i] ? k : i; };
  // ground speed of the root, central difference (one-sided at a cut)
  const spd = P.map((p, i) => {
    const ia = nb(i, -1), ib = nb(i, 1), a = P[ia], b = P[ib];
    return ib > ia ? Math.hypot(b.x - a.x, b.z - a.z) / ((ib - ia) * DT) : 0;
  });
  const air = P.map((p, i) => p.y > O.air || spd[i] > O.runSpeed);
  // velocity direction, for the catch step
  const vel = P.map((p, i) => {
    const ia = nb(i, -1), ib = nb(i, 1), a = P[ia], b = P[ib], n = (ib - ia) * DT;
    return n ? [(b.x - a.x) / n, (b.z - a.z) / n] : [0, 0];
  });
  /** A box filter over +-r samples that never reaches across a cut. */
  const blurIn = (A, r) => A.map((_, i) => {
    let s = 0, n = 0;
    for (let k = i - r; k <= i + r; k++) {
      const kk = clamp(k, 0, N - 1);
      if (piece[kk] !== piece[i]) continue;
      s += A[kk]; n++;
    }
    return s / Math.max(1, n);
  });
  // WALKING AMOUNT (0 = the fighter's footwork, 1 = a walk), from the SUSTAINED speed: the slowest speed within
  // walkHold either side, so a lunge (fast for 0.3 s) is not a walk; faded over walkBlend
  const hold = Math.max(1, Math.round(O.walkHold * RATE));
  const slow = spd.map((_, i) => {
    let m = Infinity;
    for (let k = i - hold; k <= i + hold; k++) {
      const kk = clamp(k, 0, N - 1);
      if (piece[kk] !== piece[i]) continue;
      m = Math.min(m, air[kk] ? 0 : spd[kk]);
    }
    return m === Infinity ? 0 : m;
  });
  const wk = blurIn(slow.map((v) => ss(clamp((v - O.walkFrom) / (O.walkFull - O.walkFrom), 0, 1))),
    Math.max(1, Math.round(O.walkBlend * RATE)));
  // RUN AMOUNT (0 below runFrom, 1 from runFull), from the same sustained speed. It is exactly 0 on every walk, so
  // nothing below changes a walk: every run term is gated on it.
  const rn = blurIn(slow.map((v) => ss(clamp((v - O.runFrom) / (O.runFull - O.runFrom), 0, 1))),
    Math.max(1, Math.round(O.walkBlend * RATE)));
  const running = (k) => rn[clamp(k, 0, N - 1)] > 0.5;
  const runV = (k) => Math.max(O.runFrom, spd[clamp(k, 0, N - 1)]);
  const runStep = (v) => 60 / clamp(O.runCadence[0] + O.runCadence[1] * v, O.runCadence[2], O.runCadence[3]);   // s
  const runTc = (v) => O.runContact[0] + O.runContact[1] / v;                                                    // s
  // the walking stance: the feet side by side (the alternation makes the fore-aft) and no weight on one of them
  const stanceAt = (i) => P[i].stance * (1 - wk[i]), weightAt = (i) => P[i].weight * (1 - wk[i]);
  const nomR = P.map((p, i) => nominal({ ...p, stance: stanceAt(i) }, -1));
  const nomL = P.map((p, i) => nominal({ ...p, stance: stanceAt(i) }, 1));
  const swingN = Math.max(1, Math.round(O.swing * RATE));
  const gapN = Math.max(1, Math.round(O.gap * RATE)), minN = Math.max(1, Math.round(O.minContact * RATE));
  /** The swing that starts after sample j (samples): the fighter's quick step, or a walking swing from the speed. */
  const swingAt = (j) => {
    const k = clamp(j, 0, N - 1), w = wk[k];
    if (w <= 0) return swingN;
    const walk = clamp(O.swingK / Math.max(0.1, spd[k]), O.swing, O.swingMax);
    const r = rn[k];
    if (r > 0) {                                        // a run: the swing is the stride less the contact
      const v = runV(k), run = 2 * runStep(v) - runTc(v), wl = O.swing + (walk - O.swing) * w;
      return Math.max(1, Math.round((wl + (run - wl) * r) * RATE));
    }
    return Math.max(1, Math.round((O.swing + (walk - O.swing) * w) * RATE));
  };
  /** How far the body may pass a plant started at sample i (m): half a stride, longer the faster a walk goes. */
  const reachAt = (i) => {
    const w = wk[i];
    if (w <= 0) return O.reach;
    const [a, b, lo, hi] = O.reachWalk;
    const wr = O.reach + (clamp(a + b * spd[i], lo, hi) - O.reach) * w;
    if (rn[i] > 0) { const v = runV(i); return wr + (v * runTc(v) / 2 - wr) * rn[i]; }   // half the travel in a contact
    return wr;
  };

  /** plantHolds: how much a sample counts toward a plant, 1 / (0.02 + the nominal foot's speed in m/s): a hold ~50x. */
  const holdW = (nom, k) => {
    const a = nom[nb(k, -1)], b = nom[nb(k, 1)];
    return 1 / (0.02 + Math.hypot(b[0] - a[0], b[2] - a[2]) * RATE / 2);
  };
  /** The samples where a foot of these contacts is in a STEP (between two plants of one piece, no air between). */
  function stepping(cs) {
    const sw = new Uint8Array(N);
    for (let k = 0; k + 1 < cs.length; k++) {
      const c0 = cs[k], c1 = cs[k + 1];
      if (piece[c0.b] !== piece[c1.a]) continue;
      let leap = false;
      for (let q = c0.b + 1; q < c1.a; q++) if (air[q]) { leap = true; break; }
      if (!leap) for (let q = c0.b + 1; q < c1.a; q++) sw[q] = 1;
    }
    return sw;
  }

  /** Cut the ground time into contacts: [{ a, b, pos }] (a..b inclusive, pos = the plant). `other`: the other
   *  foot's contacts. A walk ALTERNATES: this foot never lifts while the other one is stepping or about to (two feet
   *  off the ground together at walking speed is a hop: 27 Nov, Musashi hopped through both of his walks, 16 steps,
   *  because after a hold both contacts ended on the same frame and stayed in step). When its lift would clash, the
   *  step moves into the middle of the other foot's stance (an even gait), or else to the latest clear moment. */
  function contacts(nom, firstEnd, other) {
    const out = [];
    const oSw = other ? stepping(other) : null;
    const clash = (j) => {
      for (let q = Math.max(0, j + 1 - gapN); q <= Math.min(N - 1, j + swingAt(j) + gapN); q++) if (oSw[q]) return q;
      return -1;
    };
    /** The last sample of the longest contact from i whose nominal foot stays within `reach` of its mean (the body may
     *  pass over the plant, but never further than half a stride); i - 1 if not even one sample holds. */
    const grow = (i, reach, cap, turn = O.turnStep) => {
      if (O.plantHolds && wk[i] < 0.5) return growHold(i, reach, cap, turn);
      let sx = 0, sz = 0, n = 0, j = i - 1;
      for (let k = i; k <= Math.min(cap, N - 1); k++) {
        if (air[k] || piece[k] !== piece[i]) break;
        if (Math.abs(wrap(P[k].ry - P[i].ry)) > turn) break;   // the body has turned too far over this foot
        const mx = (sx + nom[k][0]) / (n + 1), mz = (sz + nom[k][2]) / (n + 1);
        let bad = false;
        for (let q = i; q <= k; q++) if (Math.hypot(nom[q][0] - mx, nom[q][2] - mz) > reach) { bad = true; break; }
        if (bad) break;
        sx += nom[k][0]; sz += nom[k][2]; n++; j = k;
      }
      return j;
    };
    /** plantHolds: the contact grows while every sample is within reach of the STILLNESS-weighted mean; after it has
     *  held still (0.1 s), within holdTol of that hold. */
    const growHold = (i, reach, cap, turn) => {
      let sx = 0, sz = 0, sw = 0, j = i - 1, still = 0, held = false;
      for (let k = i; k <= Math.min(cap, N - 1); k++) {
        if (air[k] || piece[k] !== piece[i]) break;
        if (Math.abs(wrap(P[k].ry - P[i].ry)) > turn) break;
        const w = holdW(nom, k), mx = (sx + nom[k][0] * w) / (sw + w), mz = (sz + nom[k][2] * w) / (sw + w);
        const r = held ? O.holdTol : reach;
        let bad = false;
        for (let q = i; q <= k; q++) if (Math.hypot(nom[q][0] - mx, nom[q][2] - mz) > r + (held && q < k ? reach : 0)) { bad = true; break; }
        if (!bad && held && Math.hypot(nom[k][0] - mx, nom[k][2] - mz) > O.holdTol) bad = true;
        if (bad) break;
        sx += nom[k][0] * w; sz += nom[k][2] * w; sw += w; j = k;
        still = w > 1 / (0.02 + O.holdSpeed) ? still + 1 : 0;
        if (still >= Math.round(0.1 * RATE)) held = true;
      }
      return j;
    };
    let i = 0;
    while (i < N) {
      if (air[i]) { i++; continue; }
      let sx = 0, sz = 0, n = 0, swingFit = 0;
      const cap = out.length === 0 && firstEnd != null ? firstEnd : N - 1;
      const reach = reachAt(i);
      let j = grow(i, reach, cap);
      if (j < i) { i++; continue; }                     // one frame cannot even hold itself: treat as air
      const step = j + 1 < N && !air[j + 1] && piece[j + 1] === piece[i];     // a step follows (not a leap, cut, end)
      // AN EVEN WALK (28 Nov). At a steady pace each foot keeps its own rhythm, so the two stay as far apart in time
      // as the walk's first steps put them: on Episode 1's walk-away the left foot lifted 0.02 s after the right one
      // landed and then both stood for 0.42 s, a limp. While walking this foot lifts HALF WAY between two lifts of the
      // other one, standing up to half a reach longer than its stride if it must (the body leans past the plant a
      // little further; the raised heel pays for the reach), or shorter.
      if (oSw && step && wk[j] > 0.5) {
        let s0 = -1, s1 = -1;                           // the other foot's lift before this one's end, and its next
        for (let k = 0; k < other.length; k++) {
          const lift = other[k].b + 1;
          if (lift <= j) s0 = lift; else { if (s0 >= 0) s1 = lift; break; }
        }
        if (s0 >= 0 && s1 > s0 && oSw[s0] && oSw[s1]) {
          const ideal = Math.round((s0 + s1) / 2) - 1, jMax = grow(i, reach * 1.5, cap);
          // a RUN lifts half way between the other foot's lifts too, but the other foot IS in the air then (the flight):
          // no clash rule, only that this contact may not outlast the other foot's swing (both feet down is a walk)
          if (running(j)) { if (ideal >= i + Math.round(0.06 * RATE) - 1 && ideal <= jMax) j = ideal; }
          else if (ideal >= i + minN - 1 && ideal <= jMax && clash(ideal) < 0) j = ideal;
        }
      }
      const q0 = oSw && step && !running(j) ? clash(j) : -1;
      if (q0 >= 0) {
        // an even walk: this foot lifts HALF A STEP PERIOD before the other foot's clashing lift. The period is the
        // other foot's own (its lift to its next lift, when that is a step too), else the one its speed implies (a
        // contact covers about 2 x reach of travel). Centring on the other's stance limped (0.43 / 0.77 s) whenever
        // that stance began in a hold.
        let k0 = -1;
        for (let k = 0; k < other.length; k++) if (other[k].b < q0) k0 = k; else break;
        let jt = -1;
        if (k0 >= 0) {
          const s0 = other[k0].b + 1;
          const v = Math.max(0.3, Math.hypot(vel[Math.min(N - 1, s0)][0], vel[Math.min(N - 1, s0)][1]));
          let T = Math.round((2 * reachAt(Math.min(N - 1, s0)) / v) * RATE) + swingAt(s0 - 1);
          const nx = other[k0 + 1];
          if (nx && nx.b + 2 < N && oSw[nx.b + 1] && nx.b + 1 - s0 < 2 * T) T = nx.b + 1 - s0;
          jt = Math.round(s0 - T / 2) - 1;               // this contact's last sample: the foot lifts at jt + 1
        }
        if (!(jt >= i + minN - 1 && jt < j && clash(jt) < 0)) {
          jt = -1;
          for (let q = j - 1; q >= i + minN - 1; q--) if (clash(q) < 0) { jt = q; break; }
        }
        // no slot with a gap either side: the latest one where the two swings at least do not overlap. After a cut (or
        // a long stand) both feet start a contact together and a walking swing (0.46 s) left no gapped slot: both feet
        // lifted together on every step of Episode 1's beach walk (28 Nov: 5 hops, the hips bobbing 13 cm)
        if (jt < 0) {
          const overlap = (q) => { for (let r = q + 1; r <= Math.min(N - 1, q + swingAt(q)); r++) if (oSw[r]) return true; return false; };
          for (let q = j - 1; q >= i + minN - 1; q--) if (!overlap(q)) { jt = q; break; }
        }
        // still nothing: a QUICKER swing that fits between the other foot's two swings (a stopping step). At the end of
        // Episode 1's beach walk the window was 0.43 s and the walking swing 0.44 s: both feet were off together
        if (jt < 0) {
          for (let q = j - 1; q >= i + minN - 1; q--) {
            if (oSw[q + 1]) continue;                   // the other foot is in the air right now
            let r = q + 1;
            while (r < N && !oSw[r]) r++;               // the other's next swing starts at r
            if (r - (q + 1) >= swingN + 1) { jt = q; swingFit = Math.min(swingAt(q), r - (q + 1) - 1); break; }
          }
        }
        // or this foot STANDS a moment longer (up to 0.15 s, within half a reach more and a looser turn) until the other
        // is down: in a turn on the spot the 50 deg limit ended a plant one sample before the other foot landed
        if (jt < 0) {
          const jMax2 = Math.min(grow(i, reach * 1.5, cap, O.turnStep * 1.4), j + Math.round(0.15 * RATE));
          for (let q = j + 1; q <= jMax2; q++) {
            if (oSw[q] || oSw[q + 1]) continue;          // the other foot is still in the air
            let r = q + 1, free = true;
            for (; r <= Math.min(N - 1, q + swingAt(q)); r++) if (oSw[r]) { free = false; break; }
            if (free) { jt = q; break; }
          }
        }
        if (jt >= 0) j = jt;
      }
      if (O.plantHolds && wk[i] < 0.5) for (let k = i; k <= j; k++) { const w = holdW(nom, k); sx += nom[k][0] * w; sz += nom[k][2] * w; n += w; }
      else for (let k = i; k <= j; k++) { sx += nom[k][0]; sz += nom[k][2]; n++; }   // the plant: the mean of the path
      const mid = (i + j) >> 1;
      // a walk passes over its plant: no catch step; a RUN plants behind the middle of its contact (runPlant seconds of
      // travel): the foot lands closer under the body than it leaves it (the heel-up toe-off reaches further back)
      const lead = O.lead * (1 - wk[mid]) + (rn[mid] > 0 ? O.runPlant * rn[mid] : 0);
      const pos = [sx / n + vel[mid][0] * lead, LEG.footY, sz / n + vel[mid][1] * lead];
      const pv = out[out.length - 1];
      // plantHolds: a "step" that lands where it lifted (a settle swung the nominal foot out and back) is no step: the
      // foot stays down (28 Nov, the gallery: such a step in place left no slot for the next real step, a hop)
      let same = false;
      if (O.plantHolds && pv && wk[i] < 0.5 && piece[pv.b] === piece[i] && Math.hypot(pos[0] - pv.pos[0], pos[2] - pv.pos[2]) < O.holdTol
        && Math.abs(wrap(P[mid].ry - pv.ry)) < 0.2) {
        same = true;
        for (let q = pv.b + 1; q < i; q++) if (air[q]) { same = false; break; }
      }
      if (same) {
        // the merged plant is long now: if its end still lifts into the other foot's step, it lifts earlier instead
        if (oSw && step && clash(j) >= 0) {
          for (let q = j - 1; q >= pv.a + minN - 1; q--) if (clash(q) < 0) { j = q; swingFit = 0; break; }
        }
        pv.b = j;
      } else out.push({ a: i, b: j, pos, ry: P[mid].ry });
      let ni = j + 1 + (swingFit > 0 ? swingFit : swingAt(j));   // the swing, unless a cut comes first: then plant at once
      for (let q = j + 1; q < Math.min(ni, N); q++) if (piece[q] !== piece[j]) { ni = q; break; }
      i = ni;
    }
    return out;
  }
  const cR = contacts(nomR, null, null);
  // stagger the left foot: its first contact ends halfway through the right foot's first one; then it alternates
  const cL = contacts(nomL, cR.length ? Math.max(0, (cR[0].a + cR[0].b) >> 1) : null, cR);

  /** A step (not a leap, not across a cut) between two plants. */
  const stepBetween = (c0, c1) => {
    if (!c0 || !c1 || piece[c0.b] !== piece[c1.a]) return false;
    for (let i = c0.b + 1; i < c1.a; i++) if (air[i]) return false;
    return true;
  };

  /** Fill a per-sample path: planted inside a contact, a lifted arc between two, nominal in the air. Returns the ankle
   *  path ([x, y, z, planted]) and the foot's pitch (+ toe up) per sample. */
  function path(cs, nom) {
    const out = nom.map((q) => [q[0], q[1], q[2], 0]);
    const pit = new Float64Array(N);
    const yaw = P.map((p) => p.ry);                    // each foot's own direction (the body's, in the air)
    const rampN = Math.max(1, Math.round(O.ramp * RATE));
    const done = new Array(N).fill(false);
    // THE PLANTS. A walking foot ROLLS (scaled by the walking amount; a fighter's foot stays flat): it lands on its
    // heel with the toe up and slaps flat over `loading` (the ankle turning about the heel), and before it leaves the
    // heel rises and the ankle turns about the toe (with no toe joint a rigid sandal pivots on its tip). The foot is
    // on the ground (planted) all the while; the raised heel lengthens the trailing leg, so the hips sink less.
    for (let k = 0; k < cs.length; k++) {
      const c = cs[k], len = c.b - c.a + 1;
      const r = rn[(c.a + c.b) >> 1], mixR = (wv, rv) => (r > 0 ? wv + (rv - wv) * r : wv);   // a run's foot roll
      const lN = stepBetween(cs[k - 1], c) ? Math.min(Math.round(mixR(O.loading, O.runLoading) * RATE), Math.floor(len * 0.4)) : 0;
      const hN = stepBetween(c, cs[k + 1]) ? Math.max(0, Math.min(Math.round(mixR(O.heelOff, O.runHeelOff) * len), Math.round(0.3 * RATE), len - lN - 1)) : 0;
      const hs = mixR(O.heelStrike, O.runStrike), to = mixR(O.toeOff, O.runToeOff);
      for (let i = c.a; i <= c.b; i++) {
        let th = 0, pv = 0;
        if (i < c.a + lN) { th = hs * wk[i] * (1 - ss((i - c.a) / lN)); pv = -1; }
        else if (hN > 0 && i > c.b - hN) { const u = (i - (c.b - hN)) / hN; th = -to * wk[i] * u * u; pv = 1; }
        pit[i] = th;
        const a = pivotAnkle(c.pos, c.ry, th, pv);
        yaw[i] = c.ry;
        out[i] = [a[0], a[1], a[2], 1]; done[i] = true;
      }
    }
    // THE GAPS between two plants
    for (let k = 0; k + 1 < cs.length; k++) {
      const c = cs[k], nx = cs[k + 1];
      if (nx.a <= c.b + 1) continue;
      if (piece[c.b] !== piece[nx.a]) {                 // a cut between the plants: no step across it; the foot stays
        for (let i = c.b + 1; i < nx.a; i++) {          // planted until the cut and is at its new plant after it
          if (piece[i] !== piece[c.b]) break;
          out[i] = [out[c.b][0], out[c.b][1], out[c.b][2], 1]; pit[i] = pit[c.b]; yaw[i] = c.ry; done[i] = true;
        }
        continue;
      }
      // the gap between two plants is ONE eased arc: lift, travel, reach down, land. Eased at both
      // ends, so the foot is high before it travels and a "planted" foot never races along the ground.
      let leap = false;
      for (let i = c.b + 1; i < nx.a; i++) if (air[i]) leap = true;
      const span = Math.hypot(nx.pos[0] - c.pos[0], nx.pos[2] - c.pos[2]);
      // a step lifts with its length; a leap or a lunge lifts with its time (never a balloon)
      let h = leap ? clamp(0.9 * (nx.a - c.b) * DT, O.flight, 0.5) : clamp(span * 0.28, 0.02, O.lift);
      const sl = leap ? 0 : clamp(P[(c.b + nx.a) >> 1].slide ?? 0, 0, 1);   // a sliding step skims the floor
      if (sl > 0) h += (O.slideLift - h) * sl;
      // a WALKING swing goes from the toe-off ankle (heel up) to the heel-strike ankle (toe up), low: the line between
      // them plus a small lift early in the swing (the knee folds as the thigh comes through), the foot turning from
      // heel-up to toe-up on the way. A fighter's step (walking amount 0) is the flat arc above, as before.
      // The WALKING swing, as a gait lab draws it: after toe-off the heel keeps rising a little (the knee folds to 50-60
      // deg and the foot hangs behind it), the foot levels and the toe passes 2-3 cm over the ground at mid-swing, then
      // the leg reaches and the foot turns toe-up to land on its heel. Three smooth legs through those heights. (A line
      // from the toe-off ankle carried the toe 6 cm over the ground, a high step; an early drop left the heel skimming
      // the sand for the last 0.1 s, a shuffle.)
      const A = out[c.b], B = out[nx.a], w = leap ? 0 : wk[(c.b + nx.a) >> 1];
      const eo = (x) => 1 - (1 - x) * (1 - x);
      const yRise = A[1] + O.swingRise, yMid = B[1] + O.swingMid;
      const yWalk = (u) => (u < 0.22 ? A[1] + (yRise - A[1]) * ss(u / 0.22)
        : u < 0.55 ? yRise + (yMid - yRise) * ss((u - 0.22) / 0.33) : yMid + (B[1] - yMid) * ss((u - 0.55) / 0.45));
      // A RUNNING swing: the heel comes up behind (the knee folds past 90 deg) while the body runs on, then the leg
      // sweeps through and reaches for the next plant: the foot peaks high behind and early, travels late
      const rr = leap ? 0 : rn[(c.b + nx.a) >> 1];
      const hR = rr > 0 ? clamp(O.runLift[0] + O.runLift[1] * runV((c.b + nx.a) >> 1), O.runLift[2], O.runLift[3]) : 0;
      for (let i = c.b + 1; i < nx.a; i++) {
        const u = (i - c.b) / (nx.a - c.b);
        let s = ss(u);
        const yOld = (leap ? nom[i][1] : LEG.footY) + h * Math.sin(Math.PI * u);
        let y = yOld + (yWalk(u) - yOld) * w;
        if (rr > 0) {
          const yRun = A[1] + (B[1] - A[1]) * u + hR * Math.sin(Math.PI * Math.pow(u, 0.75));
          y += (yRun - y) * rr;
          s += (u * u * (2 - u) - s) * rr;               // leaves at once (the body runs on), sweeps through late
        }
        out[i] = [A[0] + (B[0] - A[0]) * s, y, A[2] + (B[2] - A[2]) * s, 0];
        yaw[i] = c.ry + wrap(nx.ry - c.ry) * s;        // the swinging foot turns to its next plant's direction
        pit[i] = leap ? 0 : pit[c.b] * (1 - eo(Math.min(1, u / 0.5))) + pit[nx.a] * ss(clamp((u - 0.4) / 0.6, 0, 1));
        done[i] = true;
      }
    }
    // air with no plant on one side (the film opens or ends off the ground): follow the body, lifted
    for (let i = 0; i < N;) {
      if (!air[i] || done[i]) { i++; continue; }
      let j = i; while (j + 1 < N && air[j + 1] && !done[j + 1]) j++;
      const r = Math.min(rampN, Math.max(1, (j - i + 1) >> 1));
      for (let k = i; k <= j; k++) {
        const up = O.flight * ss(Math.min(1, (k - i + 1) / r, (j - k + 1) / r));
        out[k] = [nom[k][0], nom[k][1] + up, nom[k][2], 0];
      }
      i = j + 1;
    }
    return { out, pit, yaw };
  }
  const PR = path(cR, nomR), PL = path(cL, nomL), fR = PR.out, fL = PL.out;

  // THE WALK'S PHASE: 0 at each right heel strike, pi at each left one (2 pi more when one foot steps twice), linear
  // in between; it times the hips' sway and turn and the arms' swing
  const strikes = [];
  for (const [cs, side] of [[cR, 0], [cL, 1]])
    for (let k = 1; k < cs.length; k++) if (stepBetween(cs[k - 1], cs[k])) strikes.push([cs[k].a, side]);
  strikes.sort((a, b) => a[0] - b[0]);
  const phs = new Float64Array(N);
  if (strikes.length) {
    const at = [[strikes[0][0], strikes[0][1] ? Math.PI : 0]];
    for (let k = 1; k < strikes.length; k++)
      at.push([strikes[k][0], at[k - 1][1] + (strikes[k][1] !== strikes[k - 1][1] ? Math.PI : 2 * Math.PI)]);
    for (let i = 0, q = 0; i < N; i++) {
      while (q + 1 < at.length && at[q + 1][0] <= i) q++;
      phs[i] = i <= at[0][0] || q + 1 >= at.length ? at[q][1]
        : at[q][1] + (at[q + 1][1] - at[q][1]) * (i - at[q][0]) / (at[q + 1][0] - at[q][0]);
    }
  }

  // ---- weight: reach (hips must drop to keep a pinned foot) + centre of mass over the support ----
  const maxD = (LEG.thigh + LEG.shin) * 0.985;
  const addC = new Array(N).fill(0), addRx = new Array(N).fill(0), addRz = new Array(N).fill(0);
  for (let i = 0; i < N; i++) {
    const p = P[i], c = Math.cos(p.ry), s = Math.sin(p.ry);
    const hipZ = weightAt(i) * stanceAt(i) * 0.35, hipY = LEG.hipY - (p.crouch - O.walkLift * wk[i]) - 0.02;
    let drop = 0;
    const sup = [];                                   // planted feet, in the root's frame
    for (const [f, side] of [[fR[i], -1], [fL[i], 1]]) {
      const dx = f[0] - p.x, dz = f[2] - p.z;
      const lx = dx * c - dz * s, lz = dx * s + dz * c;     // inverse of the y-rotation above
      // a RUNNING leg reaches for its plant before it lands (the flight): the hips come down to the swinging foot too
      if (!f[3] && !(rn[i] > 0 && O.runReachDrop)) continue;
      if (f[3]) sup.push([lx, lz]);
      const h = Math.hypot(lx - side * 0.1, lz - hipZ);
      const reach = f[1] - p.y + Math.sqrt(Math.max(0, maxD * maxD - h * h));
      if (f[3] || h < maxD) drop = Math.max(drop, hipY - reach);
    }
    let mz = 0, mx = 0;
    if (sup.length) {                                 // overhang of the centre of mass (above the hips)
      const zs = sup.map((q) => q[1]), xs = sup.map((q) => q[0]);
      const z0 = Math.min(...zs) - O.sole[1], z1 = Math.max(...zs) + O.sole[1];
      const x0 = Math.min(...xs) - O.sole[0], x1 = Math.max(...xs) + O.sole[0];
      mz = hipZ > z1 ? hipZ - z1 : hipZ < z0 ? hipZ - z0 : 0;
      mx = 0 > x1 ? -x1 : 0 < x0 ? -x0 : 0;
    }
    // STATIC balance is for the fighter: a body whose centre leaves its feet is falling. A walking body is outside its
    // one standing foot all the time (after the back foot leaves, the front foot is ahead of the hips) and carries
    // over it on its momentum: the falling rule dropped the hips 5.7 cm and leaned them back at every toe-off (28 Nov)
    const st = 1 - wk[i];
    addC[i] = clamp(Math.max(0, drop) + O.drop * Math.abs(mz) * st, 0, O.maxDrop);
    addRx[i] = clamp(O.lean * mz * st, -O.maxLean, O.maxLean);
    addRz[i] = clamp(-O.lean * mx * st, -O.maxLean, O.maxLean);
  }
  // smooth the hip/lean pass (a box filter) so a new contact never pops, within one piece of continuity (the box
  // never averages the hips of two places across a cut)
  const win = Math.max(1, Math.round(O.smooth * RATE));
  const blur = (A) => A.map((_, i) => {
    let s = 0, n = 0;
    for (let k = i - win; k <= i + win; k++) {
      const kk = clamp(k, 0, N - 1);
      if (piece[kk] !== piece[i]) continue;
      s += A[kk]; n++;
    }
    return s / Math.max(1, n);
  });
  // the hips' drop is DILATED before the blur (the deepest drop within the window, then averaged): a plain average
  // left the hips higher than a pinned foot could reach at the deepest moment and the soft IK stretched the leg 4.8% to
  // make up (28 Nov, the walking gait's long double support)
  const dw = Math.round(win * O.dilate);
  const dil = (A) => A.map((_, i) => {
    let m = A[i];
    for (let k = i - dw; k <= i + dw; k++) { const kk = clamp(k, 0, N - 1); if (piece[kk] === piece[i] && A[kk] > m) m = A[kk]; }
    return m;
  });
  // WALKING hips: the smoothest curve that never stands higher than a pinned foot can reach, the hips' vertical
  // acceleration capped at hipAccel (the upper envelope of parabolas under each sample's required drop), lightly
  // smoothed at the joins. It dips only where the legs demand it (the double support) and rises at once after: the
  // box average held the hips low +-0.16 s around each strike and the standing knee bent 43 deg (human 15-20).
  const env = new Float64Array(N), reachN = Math.ceil(Math.sqrt(O.maxDrop / O.hipAccel) * RATE);
  for (let i = 0; i < N; i++) {
    if (wk[i] <= 0) continue;
    let m = addC[i];
    for (let k = Math.max(0, i - reachN); k <= Math.min(N - 1, i + reachN); k++) {
      if (piece[k] !== piece[i]) continue;
      const d = (k - i) * DT, v = addC[k] - O.hipAccel * d * d;
      if (v > m) m = v;
    }
    env[i] = m;
  }
  const sEnv = blurIn(Array.from(env), Math.max(1, Math.round(0.03 * RATE)));
  const sFight = blur(dil(addC));
  const sC = sFight.map((v, i) => v + ((sEnv[i] ?? 0) - v) * wk[i]), sRx = blur(addRx), sRz = blur(addRz);
  // RUNNING hips: a spring-mass bounce. They sink runBob at mid-stance (the stance knee flexes to ~40 deg) and ride
  // high (the walking lift) through the flight, and never stand higher than a planted foot can reach
  if (rn.some((v) => v > 0)) {
    const bob = new Float64Array(N);
    for (const cs of [cR, cL]) for (const c of cs) {
      if (!(rn[(c.a + c.b) >> 1] > 0)) continue;
      for (let i = c.a; i <= c.b; i++) bob[i] = Math.max(bob[i], O.runSink + O.runBob * Math.sin(Math.PI * (i - c.a + 0.5) / (c.b - c.a + 1)));
    }
    const req = blurIn(dil(addC), Math.max(1, Math.round(0.02 * RATE)));
    const runC = blurIn(Array.from(bob, (b, i) => Math.max(b, req[i])), Math.max(1, Math.round(0.025 * RATE)));
    for (let i = 0; i < N; i++) if (rn[i] > 0) sC[i] += (runC[i] - sC[i]) * rn[i];
  }

  const lerp3 = (A, i, j, u) => [A[i][0] + (A[j][0] - A[i][0]) * u, A[i][1] + (A[j][1] - A[i][1]) * u,
    A[i][2] + (A[j][2] - A[i][2]) * u];
  const out = (t) => {
    const p = motion(t);
    const g = clamp(t * RATE, 0, N - 1), i = Math.min(N - 2, Math.floor(g)), j = i + 1;
    let u = g - i;
    // never blend the plan of two places: in the last 1/120 s before the cut the hips dropped halfway to the new
    // place's stride and the oar tip moved at 17 m/s (a whoosh on the cut, a smear in the motion blur)
    if (piece[i] !== piece[j]) u = cuts.reduce((k, [, b]) => k + (t >= b - 1e-6 ? 1 : 0), 0) === piece[j] ? 1 : 0;
    const L = (A) => A[i] + (A[j] - A[i]) * u;
    const w = L(wk);
    p.stance *= 1 - w;                                 // the walking stance, as planned
    p.weight *= 1 - w;
    p._feet = { r: lerp3(fR, i, j, u), l: lerp3(fL, i, j, u), rc: fR[u < 0.5 ? i : j][3], lc: fL[u < 0.5 ? i : j][3],
      pr: L(PR.pit), pl: L(PL.pit), soft: 0.94 + (O.walkSoft - 0.94) * w,
      yr: PR.yaw[i] + wrap(PR.yaw[j] - PR.yaw[i]) * u, yl: PL.yaw[i] + wrap(PL.yaw[j] - PL.yaw[i]) * u, twist: O.footTwist };
    p.crouch += L(sC) - O.walkLift * w;
    p.rx += L(sRx);
    p.rz += L(sRz);
    if (w > 1e-4) {
      // the walk above the legs: the body rides over the standing foot, the waist turns with the forward leg and the
      // chest turns back against it (the head keeps looking ahead), the free arms swing against the legs
      const ph = L(phs), c = Math.cos(p.ry), s = Math.sin(p.ry);
      const r = L(rn);
      const mixR = (wv, rv) => (r > 0 ? wv + (rv - wv) * r : wv);
      const side = -mixR(O.hipSway, O.runSway) * w * Math.sin(ph);       // the figure's own x: + is its left
      p.x += side * c;
      p.z -= side * s;
      const yaw = mixR(O.hipYaw, O.runYaw) * w * Math.cos(ph);
      p.ty = (p.ty ?? 0) + yaw;
      p.cy = (p.cy ?? 0) - O.chestCounter * yaw;
      p.hy = (p.hy ?? 0) + (O.chestCounter - 1) * yaw;
      const arm = mixR(O.armSwing, O.runArm);
      p.rsx += arm * GA[0] * w * Math.cos(ph);   // - is forward: the right arm back as the right foot lands
      p.lsx -= arm * GA[1] * w * Math.cos(ph);
      if (r > 0) {
        // the run: the body leans into the speed (the head comes back up a little to look ahead) and a free arm pumps
        // with a bent elbow, its swing centred a little forward
        const v = Math.max(O.runFrom, L(spd)), lean = Math.min(O.runLean[2], O.runLean[0] + O.runLean[1] * v) * r;
        p.tx += lean;
        p.hx = (p.hx ?? 0) - lean * 0.5;
        const ar = Math.min(1, GA[0]) * r, al = Math.min(1, GA[1]) * r;
        p.rex += (O.runElbow - p.rex) * ar; p.rsx += O.runArmFwd * ar;
        p.lex += (O.runElbow - p.lex) * al; p.lsx += O.runArmFwd * al;
      }
    }
    return p;
  };
  out.plan = { contactsR: cR, contactsL: cL, rate: RATE, opts: O, air, walk: wk, pitchR: PR.pit, pitchL: PL.pit, phase: phs, drop: addC, hips: sC, run: rn };
  out.cuts = motion.cuts;
  out.side = motion.side;
  return out;
}
