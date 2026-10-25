// Headless controller comparison: every controller faces exactly the same
// random arrivals (same seeds), so differences come from the control logic.

import { Simulation, DEFAULT_DEMAND } from './engine.js';

/**
 * @param {object} [opts]
 * @param {string[]} [opts.controllers]
 * @param {number} [opts.duration=900] simulated seconds per run
 * @param {number[]} [opts.seeds=[1,2,3]]
 * @param {{N:number,E:number,S:number,W:number}} [opts.demand]
 * @returns {{controller:string, avgWait:number, maxWait:number, throughputPerHour:number, avgQueue:number, served:number, runs:number}[]}
 */
export function runBenchmark({
  controllers = ['fixed', 'actuated', 'maxpressure'],
  duration = 900,
  seeds = [1, 2, 3],
  demand = DEFAULT_DEMAND,
} = {}) {
  return controllers.map((controller) => {
    const acc = { avgWait: 0, maxWait: 0, throughputPerHour: 0, avgQueue: 0, served: 0 };
    for (const seed of seeds) {
      const sim = new Simulation({ seed, controller, demand });
      const chunk = 10;
      while (sim.time < duration - 1e-9) sim.step(Math.min(chunk, duration - sim.time));
      const s = sim.summary();
      acc.avgWait += s.avgWait;
      acc.maxWait += s.maxWait;
      acc.throughputPerHour += s.throughputPerHour;
      acc.avgQueue += s.avgQueue;
      acc.served += s.served;
    }
    const n = seeds.length || 1;
    return {
      controller,
      avgWait: acc.avgWait / n,
      maxWait: acc.maxWait / n,
      throughputPerHour: acc.throughputPerHour / n,
      avgQueue: acc.avgQueue / n,
      served: acc.served / n,
      runs: seeds.length,
    };
  });
}

/** Id of the controller with the lowest average wait. */
export function bestController(results) {
  return results.reduce((best, r) => (r.avgWait < best.avgWait ? r : best), results[0])?.controller;
}
