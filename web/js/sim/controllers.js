// Signal controllers. Each controller is consulted by the engine during a
// *_GREEN phase only and answers 'hold' (keep the current green) or 'switch'
// (start the change to the other axis via amber / all-red / red-amber).
//
// Pedestrian requests and emergency pre-emption are handled by the engine on
// top of whatever the controller decides.

/** Fixed-time plan: equal green for each axis regardless of demand. */
export class FixedTimeController {
  constructor({ green = 30 } = {}) {
    this.id = 'fixed';
    this.green = green;
  }

  decide(sim) {
    return sim.signal.phaseTime >= this.green ? 'switch' : 'hold';
  }
}

/**
 * Vehicle-actuated control: extend green while vehicles keep arriving at the
 * detector (the last 30 m before the stop line); "gap out" after 3 s without a
 * detection if the conflicting axis is waiting. Bounded by min/max green.
 */
export class ActuatedController {
  constructor({ minGreen = 8, maxGreen = 45, gap = 3, detector = 30 } = {}) {
    this.id = 'actuated';
    this.minGreen = minGreen;
    this.maxGreen = maxGreen;
    this.gap = gap;
    this.detector = detector;
    this._lastDetection = 0;
    this._phaseId = -1;
  }

  decide(sim) {
    const { phaseTime, axisGreen, phaseId } = sim.signal;
    if (phaseId !== this._phaseId) {
      // New green phase: reset the gap timer.
      this._phaseId = phaseId;
      this._lastDetection = sim.time;
    }
    if (sim.approachingWithin(axisGreen, this.detector) > 0) this._lastDetection = sim.time;
    if (phaseTime < this.minGreen) return 'hold';

    const otherWaiting = sim.demandOnAxis(otherAxis(axisGreen)) > 0;
    if (!otherWaiting) return 'hold'; // rest in green
    if (phaseTime >= this.maxGreen) return 'switch';
    return sim.time - this._lastDetection >= this.gap ? 'switch' : 'hold';
  }
}

/**
 * Max-pressure (adaptive): serve the axis with the larger queue. Switches when
 * the waiting axis' pressure exceeds the green axis' by a threshold, or after
 * a maximum green so nobody starves.
 */
export class MaxPressureController {
  constructor({ minGreen = 8, maxGreen = 60, threshold = 2 } = {}) {
    this.id = 'maxpressure';
    this.minGreen = minGreen;
    this.maxGreen = maxGreen;
    this.threshold = threshold;
  }

  decide(sim) {
    const { phaseTime, axisGreen } = sim.signal;
    if (phaseTime < this.minGreen) return 'hold';
    const other = otherAxis(axisGreen);
    if (sim.demandOnAxis(other) === 0) return 'hold'; // nobody waiting: rest in green
    if (phaseTime >= this.maxGreen) return 'switch';
    if (sim.demandOnAxis(axisGreen) === 0) return 'switch'; // green road is empty
    return sim.pressure(other) - sim.pressure(axisGreen) > this.threshold ? 'switch' : 'hold';
  }
}

/** Manual control: only switches when the user asks (sim.manualSwitch()). */
export class ManualController {
  constructor({ minGreen = 2 } = {}) {
    this.id = 'manual';
    this.minGreen = minGreen;
  }

  decide(sim) {
    if (sim._manualRequest && sim.signal.phaseTime >= this.minGreen) return 'switch';
    return 'hold';
  }
}

export function otherAxis(axis) {
  return axis === 'NS' ? 'EW' : 'NS';
}

/** Registry with display metadata for the UI. */
export const CONTROLLERS = {
  fixed: {
    id: 'fixed',
    name: 'Fixed time',
    description: 'Classic timer: 30 s of green for each road, whatever the traffic.',
    create: (opts) => new FixedTimeController(opts),
  },
  actuated: {
    id: 'actuated',
    name: 'Vehicle actuated',
    description: 'Detectors extend green while cars keep coming; gaps out after 3 s (8–45 s green).',
    create: (opts) => new ActuatedController(opts),
  },
  maxpressure: {
    id: 'maxpressure',
    name: 'Max pressure (adaptive)',
    description: 'Gives green to whichever road has the longer queue (8–60 s green).',
    create: (opts) => new MaxPressureController(opts),
  },
  manual: {
    id: 'manual',
    name: 'Manual',
    description: 'You are the signal operator: press “Switch” to change the lights.',
    create: (opts) => new ManualController(opts),
  },
};

export const CONTROLLER_IDS = Object.keys(CONTROLLERS);

/** Instantiate a controller by id ('fixed' | 'actuated' | 'maxpressure' | 'manual'). */
export function createController(name, opts) {
  const entry = CONTROLLERS[name];
  if (!entry) throw new Error(`Unknown controller "${name}". Expected one of: ${CONTROLLER_IDS.join(', ')}`);
  return entry.create(opts);
}
