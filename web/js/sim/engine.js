// GreenWave simulation engine: a 4-way junction with UK signal sequencing,
// IDM car-following, pedestrian scramble phase and emergency pre-emption.
//
// Pure JavaScript — no DOM access — so it runs identically in the browser and
// in Node (tests, benchmarks). All units are SI: metres, seconds, m/s.
//
// Coordinates for pedestrians are metres relative to the junction centre,
// x pointing east and y pointing south (screen convention).

import { Rng } from './rng.js';
import { createController, otherAxis } from './controllers.js';

export const APPROACHES = ['N', 'E', 'S', 'W']; // direction a vehicle COMES FROM
export const LANE_LENGTH = 160; // spawn point (pos = 0) to stop line
export const BOX = 24; // width of the junction box
export const EXIT_LENGTH = 160; // far side of the box to the despawn point
export const STOP_LINE = LANE_LENGTH;
export const PATH_LENGTH = LANE_LENGTH + BOX + EXIT_LENGTH;

export const AXIS_OF = { N: 'NS', S: 'NS', E: 'EW', W: 'EW' };
export const AXIS_APPROACHES = { NS: ['N', 'S'], EW: ['E', 'W'] };

/** Fixed durations (seconds) of the timed phases. Green phases are controller-driven. */
export const TIMINGS = {
  AMBER: 3,
  ALL_RED: 2,
  ALL_RED_AFTER_PED: 1,
  RED_AMBER: 2,
  PED_WALK: 7,
  PED_FLASH: 4,
  MIN_GREEN_PED: 6, // shortest green before a pedestrian request may end it
  MIN_GREEN_PREEMPT: 2, // shortest green before emergency pre-emption may end it
};

export const DEFAULT_DEMAND = { N: 0.12, S: 0.12, E: 0.08, W: 0.08 };

const MAX_SUBSTEP = 0.1;
const WAIT_SPEED = 0.5; // below this a vehicle counts as waiting
const QUEUE_SPEED = 1.0; // below this (before the stop line) a vehicle is queued
const ENTRY_CLEARANCE = 6; // metres the newest vehicle's rear must have travelled before a spawn
const HISTORY_INTERVAL = 5;
const HISTORY_CAP = 360;
const EVENT_CAP = 50;
const MAX_DECEL = 9; // physical braking limit (m/s²)
const AMBER_STOP_DECEL = 4; // comfortable enough to stop on amber

// IDM parameters.
const IDM = { a: 1.6, b: 2.0, s0: 2.0, T: 1.2, delta: 4 };

const CAR_COLORS = [
  '#e63946', '#457b9d', '#f4a261', '#2a9d8f', '#e9c46a',
  '#8d99ae', '#ef476f', '#118ab2', '#6d597a', '#b5838d',
  '#3a5a40', '#d4d4d8',
];

const PHASE_DURATION = {
  NS_AMBER: TIMINGS.AMBER,
  EW_AMBER: TIMINGS.AMBER,
  NS_RED_AMBER: TIMINGS.RED_AMBER,
  EW_RED_AMBER: TIMINGS.RED_AMBER,
  PED_WALK: TIMINGS.PED_WALK,
  PED_FLASH: TIMINGS.PED_FLASH,
};

export class Simulation {
  /**
   * @param {object} [opts]
   * @param {number} [opts.seed=42]
   * @param {string} [opts.controller='actuated'] 'fixed' | 'actuated' | 'maxpressure' | 'manual'
   * @param {{N:number,E:number,S:number,W:number}} [opts.demand] arrivals per second (Poisson) per approach
   * @param {object} [opts.controllerOptions] passed to the controller constructor
   */
  constructor(opts = {}) {
    this.seed = opts.seed ?? 42;
    this.demand = { ...DEFAULT_DEMAND, ...(opts.demand || {}) };
    this.controllerOptions = opts.controllerOptions || undefined;
    this.controllerName = opts.controller || 'actuated';
    this.controller = createController(this.controllerName, this.controllerOptions);
    this.reset(this.seed);
  }

  // ---------------------------------------------------------------- public API

  /** Clear vehicles, pedestrians and stats (settings are kept). */
  reset(seed) {
    if (seed !== undefined) this.seed = seed;
    this.rng = new Rng(this.seed);
    this.time = 0;
    this._nextId = 1;
    this._lanes = { N: [], E: [], S: [], W: [] }; // front-most vehicle first
    this._pending = { N: 0, E: 0, S: 0, W: 0 }; // arrivals that could not enter yet
    this._pendingEmergency = { N: 0, E: 0, S: 0, W: 0 };
    this._nextArrival = {};
    for (const a of APPROACHES) this._nextArrival[a] = this.rng.exponential(this.demand[a]);
    this._phaseCounter = 0;
    this._manualRequest = false;
    this._pedRequested = false;
    this._target = 'EW'; // axis to receive green after the current inter-green
    this._allRedDuration = TIMINGS.ALL_RED;
    this.signal = {
      phase: 'NS_GREEN',
      phaseTime: 0,
      axisGreen: 'NS',
      ped: false,
      next: 'EW',
      preempt: null,
      phaseDuration: null,
      cycle: 0,
      phaseId: 0,
    };
    this.pedestrians = [];
    this._nextPedId = 1;
    this.events = [];
    this._servedTimes = [];
    this._sumWaitServed = 0;
    this._maxWaitServed = 0;
    this._queueIntegral = 0;
    this._nextSample = HISTORY_INTERVAL;
    this.stats = {
      throughput: 0,
      throughputPerMin: 0,
      throughputPerHour: 0,
      avgWait: 0,
      maxWait: 0,
      queue: { N: 0, E: 0, S: 0, W: 0 },
      avgQueue: 0,
      served: 0,
      spawned: 0,
      blocked: 0,
      emergencyServed: 0,
      pedestrianPhases: 0,
      history: [],
    };
    this.vehicles = [];
    this._updateQueues();
  }

  /** Advance the simulation by dt seconds (sub-stepped at <= 0.1 s). */
  step(dt) {
    if (!(dt > 0)) return;
    let remaining = dt;
    while (remaining > 1e-9) {
      const h = Math.min(MAX_SUBSTEP, remaining);
      this._substep(h);
      remaining -= h;
    }
    this._rebuildVehicleList();
  }

  /** Light shown to an approach: 'red' | 'red_amber' | 'green' | 'amber' (UK sequence). */
  lightFor(approach) {
    const axis = AXIS_OF[approach];
    switch (this.signal.phase) {
      case `${axis}_GREEN`: return 'green';
      case `${axis}_AMBER`: return 'amber';
      case `${axis}_RED_AMBER`: return 'red_amber';
      default: return 'red';
    }
  }

  /** 'dont_walk' | 'walk' | 'flashing' for the all-red pedestrian scramble. */
  pedestrianState() {
    if (this.signal.phase === 'PED_WALK') return 'walk';
    if (this.signal.phase === 'PED_FLASH') return 'flashing';
    return 'dont_walk';
  }

  setController(name) {
    this.controller = createController(name, this.controllerOptions);
    this.controllerName = name;
    this._manualRequest = false;
    this._log('controller', `Controller → ${name}`);
  }

  setDemand(approach, vehPerSec) {
    if (!APPROACHES.includes(approach)) throw new Error(`Unknown approach "${approach}"`);
    const rate = Math.max(0, Number(vehPerSec) || 0);
    this.demand[approach] = rate;
    // Poisson arrivals are memoryless, so re-sampling from "now" is exact.
    this._nextArrival[approach] = this.time + this.rng.exponential(rate);
  }

  /** Pedestrian push-button: an all-red walk phase is served soon. */
  requestPedestrian() {
    if (this._pedRequested || this.signal.phase === 'PED_WALK') return false;
    this._pedRequested = true;
    this.signal.ped = true;
    this._log('pedestrian', 'Pedestrian button pressed — WAIT');
    return true;
  }

  /** Spawn an emergency vehicle on an approach; its axis is pre-empted to green. */
  spawnEmergency(approach) {
    if (!APPROACHES.includes(approach)) throw new Error(`Unknown approach "${approach}"`);
    this._pendingEmergency[approach]++;
    this._trySpawn(approach);
    this._log('emergency', `Emergency vehicle approaching from ${approach}`);
  }

  /** Manual mode: request switching the green axis. Returns true if accepted. */
  manualSwitch() {
    if (this.controllerName !== 'manual') return false;
    if (!this.signal.phase.endsWith('_GREEN')) return false;
    this._manualRequest = true;
    return true;
  }

  // ------------------------------------------------- helpers for controllers

  /** Vehicles queued (slow, before the stop line) plus arrivals blocked at the entry. */
  queueOnAxis(axis) {
    let q = 0;
    for (const a of AXIS_APPROACHES[axis]) q += this.stats.queue[a];
    return q;
  }

  /** Number of vehicles within `dist` metres upstream of the stop line on an axis. */
  approachingWithin(axis, dist) {
    let n = 0;
    for (const a of AXIS_APPROACHES[axis]) {
      for (const v of this._lanes[a]) {
        if (v.pos < STOP_LINE && v.pos >= STOP_LINE - dist) n++;
      }
    }
    return n;
  }

  /** Vehicles that still need to cross the stop line on an axis (incl. blocked arrivals). */
  demandOnAxis(axis) {
    let n = 0;
    for (const a of AXIS_APPROACHES[axis]) {
      n += this._pending[a] + this._pendingEmergency[a];
      for (const v of this._lanes[a]) if (v.pos < STOP_LINE) n++;
    }
    return n;
  }

  /** Pressure used by max-pressure control: queued + half the moving vehicles within 60 m. */
  pressure(axis) {
    let p = 0;
    for (const a of AXIS_APPROACHES[axis]) {
      p += this._pending[a] + this._pendingEmergency[a];
      for (const v of this._lanes[a]) {
        if (v.pos >= STOP_LINE) continue;
        if (v.speed < QUEUE_SPEED) p += 1;
        else if (v.pos >= STOP_LINE - 60) p += 0.5;
      }
    }
    return p;
  }

  /**
   * Summary metrics for benchmarking. avgWait includes vehicles still in the
   * system so a controller cannot look good by starving an approach.
   */
  summary() {
    let sum = this._sumWaitServed;
    let n = this.stats.served;
    let maxWait = this._maxWaitServed;
    for (const a of APPROACHES) {
      for (const v of this._lanes[a]) {
        if (v.pos < STOP_LINE) {
          sum += v.waitTime;
          n++;
          if (v.waitTime > maxWait) maxWait = v.waitTime;
        }
      }
    }
    return {
      time: this.time,
      avgWait: n ? sum / n : 0,
      maxWait,
      served: this.stats.served,
      throughputPerHour: this.time > 0 ? (this.stats.served / this.time) * 3600 : 0,
      avgQueue: this.time > 0 ? this._queueIntegral / this.time : 0,
      blocked: this.stats.blocked,
    };
  }

  // ------------------------------------------------------------ internals

  _substep(h) {
    this.time += h;
    this.signal.phaseTime += h;
    this._arrivals();
    this._updateSignal();
    this._moveVehicles(h);
    this._movePedestrians(h);
    this._updateQueues();
    this._queueIntegral += h * this.stats.avgQueue;
    if (this.time >= this._nextSample - 1e-9) {
      this._sample();
      this._nextSample += HISTORY_INTERVAL;
    }
  }

  _arrivals() {
    for (const a of APPROACHES) {
      while (this.time >= this._nextArrival[a]) {
        this._pending[a]++;
        this.stats.spawned++;
        this._nextArrival[a] += this.rng.exponential(this.demand[a]);
      }
      this._trySpawn(a);
    }
  }

  _trySpawn(a) {
    if (this._pending[a] + this._pendingEmergency[a] === 0) return;
    const lane = this._lanes[a];
    const last = lane[lane.length - 1];
    if (last && last.pos - last.length < ENTRY_CLEARANCE) {
      return; // entry occupied — the arrival waits off-road
    }
    const emergency = this._pendingEmergency[a] > 0;
    if (emergency) this._pendingEmergency[a]--;
    else this._pending[a]--;
    const v = this._makeVehicle(a, emergency);
    if (last) {
      // Enter no faster than is safe behind the previous vehicle.
      const gap = last.pos - last.length;
      const safe = Math.sqrt(Math.max(0, 2 * IDM.b * Math.max(0, gap - IDM.s0))) + last.speed * 0.5;
      v.speed = Math.min(v.speed, Math.max(last.speed, safe));
    }
    lane.push(v);
  }

  _makeVehicle(approach, emergency) {
    const r = this.rng;
    let kind = 'car';
    let length = r.uniform(4.2, 4.9);
    let width = 1.8;
    let v0 = 13.9 * r.uniform(0.9, 1.05);
    let color = r.pick(CAR_COLORS);
    if (emergency) {
      kind = 'emergency';
      length = 6;
      width = 2.1;
      v0 = 18;
      color = '#f8f9fa';
    } else if (r.random() < 0.07) {
      kind = 'bus';
      length = r.uniform(9, 11);
      width = 2.5;
      v0 = 12;
      color = '#f2c14e';
    }
    return {
      id: this._nextId++,
      approach,
      axis: AXIS_OF[approach],
      kind,
      pos: 0,
      speed: v0 * 0.85,
      accel: 0,
      length,
      width,
      v0,
      emergency,
      braking: false,
      waitTime: 0,
      color,
      committed: false,
      _amberEpisode: -1,
      spawnTime: this.time,
    };
  }

  /** Axis with an emergency vehicle that still has to cross the stop line, or null. */
  _emergencyAxis() {
    for (const a of APPROACHES) {
      if (this._pendingEmergency[a] > 0) return AXIS_OF[a];
      for (const v of this._lanes[a]) if (v.emergency && v.pos < STOP_LINE) return AXIS_OF[a];
    }
    return null;
  }

  _setPhase(phase) {
    const prev = this.signal.phase;
    this.signal.phase = phase;
    this.signal.phaseTime = 0;
    this.signal.phaseDuration = phase === 'ALL_RED' ? this._allRedDuration : (PHASE_DURATION[phase] ?? null);
    this.signal.axisGreen = phase.endsWith('_GREEN') ? phase.slice(0, 2) : null;
    this._phaseCounter++;
    this.signal.phaseId = this._phaseCounter;
    if (phase === 'PED_WALK') {
      this._pedRequested = false;
      this.signal.ped = false;
      this.stats.pedestrianPhases++;
      this._spawnPedestrians();
    }
    if (phase.endsWith('_GREEN') && prev.endsWith('_RED_AMBER')) this.signal.cycle += 0.5;
    if (phase.endsWith('_GREEN')) this._manualRequest = false;
  }

  _updateSignal() {
    const s = this.signal;
    const preempt = this._emergencyAxis();
    s.preempt = preempt;
    s.next = this._target;

    switch (s.phase) {
      case 'NS_GREEN':
      case 'EW_GREEN': {
        const axis = s.axisGreen;
        const other = otherAxis(axis);
        let change = false;
        if (preempt) {
          // Pre-emption overrides the controller: hold for our emergency, yield for theirs.
          if (preempt === other && s.phaseTime >= TIMINGS.MIN_GREEN_PREEMPT) {
            change = true;
            this._log('preempt', `Pre-emption: clearing the junction for ${other}`);
          }
        } else if (this._pedRequested && s.phaseTime >= TIMINGS.MIN_GREEN_PED) {
          change = true;
        } else if (this.controller.decide(this) === 'switch') {
          change = true;
        }
        if (change) {
          this._target = preempt || other;
          this._manualRequest = false;
          this._setPhase(`${axis}_AMBER`);
        }
        break;
      }
      case 'NS_AMBER':
      case 'EW_AMBER':
        if (s.phaseTime >= TIMINGS.AMBER) {
          this._allRedDuration = TIMINGS.ALL_RED;
          this._setPhase('ALL_RED');
        }
        break;
      case 'ALL_RED':
        if (preempt) this._target = preempt;
        if (s.phaseTime >= this._allRedDuration) {
          if (this._pedRequested && !preempt) this._setPhase('PED_WALK');
          else this._setPhase(`${this._target}_RED_AMBER`);
        }
        break;
      case 'PED_WALK':
        if (s.phaseTime >= TIMINGS.PED_WALK || preempt) this._setPhase('PED_FLASH');
        break;
      case 'PED_FLASH':
        if (s.phaseTime >= TIMINGS.PED_FLASH) {
          this._allRedDuration = TIMINGS.ALL_RED_AFTER_PED;
          if (preempt) this._target = preempt;
          this._setPhase('ALL_RED');
        }
        break;
      case 'NS_RED_AMBER':
      case 'EW_RED_AMBER': {
        const axis = s.phase.slice(0, 2);
        if (preempt && preempt !== axis) {
          // Red+amber still means "stop", so we can safely fall back to all-red.
          this._target = preempt;
          this._allRedDuration = TIMINGS.ALL_RED_AFTER_PED;
          this._setPhase('ALL_RED');
        } else if (s.phaseTime >= TIMINGS.RED_AMBER) {
          this._target = otherAxis(axis);
          this._setPhase(`${axis}_GREEN`);
        }
        break;
      }
      default:
        throw new Error(`Unknown phase ${s.phase}`);
    }
    s.next = this._target;
  }

  /** Does vehicle v have to treat the stop line as an obstacle right now? */
  _mustStop(v) {
    if (v.pos >= STOP_LINE || v.committed) return false;
    const light = this.lightFor(v.approach);
    if (light === 'green') return false;
    if (light === 'amber') {
      if (v._amberEpisode !== this._phaseCounter) {
        v._amberEpisode = this._phaseCounter;
        const d = STOP_LINE - v.pos;
        const needed = (v.speed * v.speed) / (2 * Math.max(d, 0.01));
        if (needed > AMBER_STOP_DECEL && d < 30) {
          v.committed = true; // cannot stop comfortably — proceed through amber
          return false;
        }
      }
      return true;
    }
    return true; // red or red+amber
  }

  _moveVehicles(h) {
    for (const a of APPROACHES) {
      const lane = this._lanes[a];
      const light = this.lightFor(a);
      let leader = null;
      for (let i = 0; i < lane.length; i++) {
        const v = lane[i];
        if (light === 'green') v.committed = false;
        const stop = this._mustStop(v);

        // Gap to the nearest obstacle: the leader's rear or the stop line.
        let gap = Infinity;
        let dv = 0;
        if (leader) {
          gap = leader.pos - leader.length - v.pos;
          dv = v.speed - leader.speed;
        }
        if (stop) {
          const g = STOP_LINE + 1 - v.pos; // stop ~1 m before the line
          if (g < gap) {
            gap = g;
            dv = v.speed;
          }
        }

        let acc = IDM.a * (1 - Math.pow(v.speed / v.v0, IDM.delta));
        if (gap < Infinity) {
          const sStar = IDM.s0 + Math.max(0, v.speed * IDM.T + (v.speed * dv) / (2 * Math.sqrt(IDM.a * IDM.b)));
          acc -= IDM.a * Math.pow(sStar / Math.max(gap, 0.1), 2);
        }
        acc = Math.max(-MAX_DECEL, acc);

        let newSpeed = v.speed + acc * h;
        let newPos;
        if (newSpeed < 0) {
          newSpeed = 0;
          newPos = v.pos + (acc < 0 ? Math.min(v.speed * h, (v.speed * v.speed) / (-2 * acc)) : 0);
        } else {
          newPos = v.pos + (v.speed + newSpeed) * 0.5 * h;
        }

        // Hard safety constraints: never pass a stop line we must stop at,
        // never overlap the vehicle ahead.
        if (stop && newPos > STOP_LINE - 0.05) {
          newPos = Math.max(v.pos, STOP_LINE - 0.05);
          newSpeed = 0;
        }
        if (leader) {
          const limit = leader.pos - leader.length - 0.5;
          if (newPos > limit) {
            newPos = Math.max(v.pos, limit);
            newSpeed = Math.min(newSpeed, leader.speed);
          }
        }

        v.accel = acc;
        v.speed = newSpeed;
        if (v.pos < STOP_LINE && newPos >= STOP_LINE) {
          v.crossedAt = this.time;
          v.crossedOn = light;
        }
        v.pos = newPos;
        v.braking = acc < -0.6 || (newSpeed < 0.3 && v.pos < STOP_LINE);
        if (v.pos < STOP_LINE && newSpeed < WAIT_SPEED) v.waitTime += h;
        leader = v;
      }

      // Despawn vehicles whose rear has left the map (they are at the front of the lane).
      while (lane.length && lane[0].pos - lane[0].length > PATH_LENGTH) {
        this._serve(lane.shift());
      }
    }
  }

  _serve(v) {
    this.stats.served++;
    this.stats.throughput = this.stats.served;
    this._sumWaitServed += v.waitTime;
    if (v.waitTime > this._maxWaitServed) this._maxWaitServed = v.waitTime;
    this._servedTimes.push(this.time);
    if (v.emergency) {
      this.stats.emergencyServed++;
      this._log('emergency', `Emergency vehicle from ${v.approach} cleared the junction`);
    }
  }

  _updateQueues() {
    let total = 0;
    let maxCurrentWait = 0;
    for (const a of APPROACHES) {
      let q = this._pending[a] + this._pendingEmergency[a];
      for (const v of this._lanes[a]) {
        if (v.pos < STOP_LINE) {
          if (v.speed < QUEUE_SPEED) q++;
          if (v.waitTime > maxCurrentWait) maxCurrentWait = v.waitTime;
        }
      }
      this.stats.queue[a] = q;
      total += q;
    }
    const st = this.stats;
    st.avgQueue = total / APPROACHES.length;
    while (this._servedTimes.length && this._servedTimes[0] < this.time - 60) this._servedTimes.shift();
    st.throughputPerMin = this._servedTimes.length * (this.time >= 60 ? 1 : 60 / Math.max(this.time, 1));
    st.throughputPerHour = this.time > 0 ? (st.served / this.time) * 3600 : 0;
    st.avgWait = st.served ? this._sumWaitServed / st.served : 0;
    st.maxWait = Math.max(this._maxWaitServed, maxCurrentWait);
    st.blocked = 0;
    for (const a of APPROACHES) st.blocked += this._pending[a];
  }

  _sample() {
    const h = this.stats.history;
    h.push({
      t: Math.round(this.time * 10) / 10,
      avgQueue: this.stats.avgQueue,
      throughputPerMin: this.stats.throughputPerMin,
      avgWait: this.stats.avgWait,
      queue: { ...this.stats.queue },
      phase: this.signal.phase,
    });
    if (h.length > HISTORY_CAP) h.splice(0, h.length - HISTORY_CAP);
  }

  _spawnPedestrians() {
    // Walkers on the four crosswalks (just inside each edge of the box).
    const half = BOX / 2;
    const edge = half - 2;
    const crossings = [
      { side: 'N', from: [-half, -edge], to: [half, -edge] },
      { side: 'S', from: [-half, edge], to: [half, edge] },
      { side: 'W', from: [-edge, -half], to: [-edge, half] },
      { side: 'E', from: [edge, -half], to: [edge, half] },
    ];
    const total = TIMINGS.PED_WALK + TIMINGS.PED_FLASH - 0.5;
    for (const c of crossings) {
      const n = this.rng.int(0, 3);
      for (let i = 0; i < n; i++) {
        const reverse = this.rng.random() < 0.5;
        const delay = this.rng.uniform(0, 3);
        const duration = this.rng.uniform(6, total - delay);
        const [from, to] = reverse ? [c.to, c.from] : [c.from, c.to];
        this.pedestrians.push({
          id: this._nextPedId++,
          side: c.side,
          from,
          to,
          x: from[0],
          y: from[1],
          progress: 0,
          delay,
          duration,
          color: this.rng.pick(['#ff6b6b', '#4dabf7', '#ffd43b', '#69db7c', '#da77f2', '#ffa94d']),
        });
      }
    }
  }

  _movePedestrians(h) {
    if (!this.pedestrians.length) return;
    for (const p of this.pedestrians) {
      if (p.delay > 0) {
        p.delay -= h;
        continue;
      }
      p.progress = Math.min(1, p.progress + h / p.duration);
      p.x = p.from[0] + (p.to[0] - p.from[0]) * p.progress;
      p.y = p.from[1] + (p.to[1] - p.from[1]) * p.progress;
    }
    // Walkers who have not started by the end of the walk phase stay on the kerb.
    const walking = this.signal.phase === 'PED_WALK';
    this.pedestrians = this.pedestrians.filter((p) => p.progress < 1 && (walking || p.delay <= 0));
  }

  _rebuildVehicleList() {
    const out = [];
    for (const a of APPROACHES) for (const v of this._lanes[a]) out.push(v);
    this.vehicles = out;
  }

  _log(type, message) {
    this.events.push({ t: Math.round(this.time * 10) / 10, type, message });
    if (this.events.length > EVENT_CAP) this.events.shift();
  }
}

/** Convenience factory mirroring the class constructor. */
export function createSim(opts) {
  return new Simulation(opts);
}
