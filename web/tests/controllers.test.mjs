import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Simulation } from '../js/sim/engine.js';
import { CONTROLLERS, CONTROLLER_IDS, createController } from '../js/sim/controllers.js';

test('registry lists the four controllers with display metadata', () => {
  assert.deepEqual(CONTROLLER_IDS, ['fixed', 'actuated', 'maxpressure', 'manual']);
  for (const id of CONTROLLER_IDS) {
    assert.equal(CONTROLLERS[id].id, id);
    assert.ok(CONTROLLERS[id].name.length > 0);
    assert.ok(CONTROLLERS[id].description.length > 0);
    assert.equal(createController(id).id, id);
  }
  assert.throws(() => createController('nope'), /Unknown controller/);
  assert.throws(() => new Simulation({ controller: 'nope' }), /Unknown controller/);
});

for (const controller of ['fixed', 'actuated', 'maxpressure']) {
  test(`${controller} serves traffic on every approach`, () => {
    const sim = new Simulation({ seed: 21, controller });
    const servedFrom = new Set();
    const seen = new Map();
    while (sim.time < 900) {
      sim.step(1);
      for (const v of sim.vehicles) seen.set(v.id, v);
    }
    for (const v of seen.values()) if (v.crossedOn) servedFrom.add(v.approach);
    assert.deepEqual([...servedFrom].sort(), ['E', 'N', 'S', 'W']);
    assert.ok(sim.stats.served > 250, `served ${sim.stats.served}`);
    assert.ok(sim.stats.avgWait < 40, `avgWait ${sim.stats.avgWait}`);
  });
}

test('fixed-time gives 30 s of green', () => {
  const sim = new Simulation({ seed: 1, controller: 'fixed' });
  while (sim.signal.phase === 'NS_GREEN') sim.step(0.1);
  assert.equal(sim.signal.phase, 'NS_AMBER');
  assert.ok(Math.abs(sim.time - 30) < 0.15, `switched at ${sim.time}`);
});

test('actuated rests in green when the other road is empty', () => {
  const sim = new Simulation({ seed: 1, controller: 'actuated', demand: { N: 0.2, S: 0.2, E: 0, W: 0 } });
  while (sim.time < 300) {
    sim.step(1);
    assert.equal(sim.lightFor('N'), 'green');
  }
});

test('max-pressure switches toward the longer queue', () => {
  const sim = new Simulation({ seed: 1, controller: 'maxpressure', demand: { N: 0, S: 0, E: 0.3, W: 0.3 } });
  let t = null;
  while (sim.time < 60 && t === null) {
    sim.step(0.1);
    if (sim.lightFor('E') === 'green') t = sim.time;
  }
  assert.ok(t !== null && t < 20, `EW green at ${t}`);
});

test('manual control only switches on request', () => {
  const sim = new Simulation({ seed: 3, controller: 'manual' });
  while (sim.time < 120) {
    sim.step(0.5);
    assert.equal(sim.signal.phase, 'NS_GREEN');
  }
  assert.equal(sim.manualSwitch(), true);
  sim.step(0.2);
  assert.equal(sim.signal.phase, 'NS_AMBER');
  assert.equal(sim.manualSwitch(), false, 'ignored outside green');
  while (sim.signal.phase !== 'EW_GREEN') sim.step(0.1);
  sim.step(30);
  assert.equal(sim.signal.phase, 'EW_GREEN', 'stays green until asked again');
  sim.setController('fixed');
  assert.equal(sim.manualSwitch(), false, 'only in manual mode');
});
