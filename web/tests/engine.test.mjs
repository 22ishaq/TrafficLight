import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  Simulation, APPROACHES, STOP_LINE, PATH_LENGTH, LANE_LENGTH, BOX, EXIT_LENGTH, AXIS_OF,
} from '../js/sim/engine.js';

const HEAVY = { N: 0.5, S: 0.5, E: 0.5, W: 0.5 };

function run(sim, seconds, dt = 0.5, each) {
  const end = sim.time + seconds;
  while (sim.time < end - 1e-9) {
    sim.step(dt);
    if (each) each(sim);
  }
}

test('geometry constants follow the contract', () => {
  assert.deepEqual(APPROACHES, ['N', 'E', 'S', 'W']);
  assert.equal(STOP_LINE, LANE_LENGTH);
  assert.equal(PATH_LENGTH, LANE_LENGTH + BOX + EXIT_LENGTH);
});

test('same seed + same calls => identical simulation', () => {
  const a = new Simulation({ seed: 7, controller: 'maxpressure' });
  const b = new Simulation({ seed: 7, controller: 'maxpressure' });
  for (let i = 0; i < 400; i++) {
    a.step(0.25);
    b.step(0.25);
    if (i === 100) { a.requestPedestrian(); b.requestPedestrian(); }
    if (i === 200) { a.spawnEmergency('E'); b.spawnEmergency('E'); }
  }
  assert.deepEqual(JSON.parse(JSON.stringify(a.vehicles)), JSON.parse(JSON.stringify(b.vehicles)));
  assert.deepEqual(a.stats, b.stats);
  assert.deepEqual(a.signal, b.signal);
});

test('different seeds give different traffic', () => {
  const a = new Simulation({ seed: 1 });
  const b = new Simulation({ seed: 2 });
  run(a, 120);
  run(b, 120);
  assert.notDeepEqual(a.vehicles.map((v) => v.pos), b.vehicles.map((v) => v.pos));
});

test('step sub-steps large dt and still advances time exactly', () => {
  const sim = new Simulation({ seed: 3 });
  sim.step(5);
  assert.ok(Math.abs(sim.time - 5) < 1e-9);
  sim.step(0);
  sim.step(-1);
  assert.ok(Math.abs(sim.time - 5) < 1e-9);
});

for (const controller of ['fixed', 'actuated', 'maxpressure']) {
  test(`no vehicle ever overlaps another under heavy demand (${controller})`, () => {
    const sim = new Simulation({ seed: 11, controller, demand: HEAVY });
    run(sim, 1200, 0.5, (s) => {
      const byLane = {};
      for (const v of s.vehicles) (byLane[v.approach] ||= []).push(v);
      for (const lane of Object.values(byLane)) {
        for (let i = 1; i < lane.length; i++) {
          const leader = lane[i - 1];
          const v = lane[i];
          const gap = leader.pos - leader.length - v.pos;
          assert.ok(gap >= -1e-6, `overlap of ${gap.toFixed(3)} m at t=${s.time} (${v.approach})`);
        }
      }
      for (const v of s.vehicles) {
        assert.ok(v.speed >= 0 && Number.isFinite(v.pos), 'speeds are non-negative and positions finite');
      }
    });
    assert.ok(sim.stats.served > 300, `served ${sim.stats.served}`);
  });

  test(`vehicles never cross the stop line on red or red+amber (${controller})`, () => {
    const sim = new Simulation({ seed: 5, controller, demand: { N: 0.3, S: 0.25, E: 0.2, W: 0.3 } });
    const seen = new Map();
    let pedCalls = 0;
    run(sim, 1800, 0.5, (s) => {
      for (const v of s.vehicles) seen.set(v.id, v);
      if (Math.floor(s.time) % 90 === 0 && pedCalls < s.time / 90) {
        pedCalls++;
        s.requestPedestrian();
      }
      // Nothing may be in the box during the pedestrian walk phase except
      // vehicles that were already committed when it began.
      if (s.signal.phase === 'PED_WALK' && s.signal.phaseTime > 1) {
        for (const v of s.vehicles) {
          const inBox = v.pos > STOP_LINE && v.pos - v.length < STOP_LINE + BOX;
          assert.ok(!inBox, `vehicle ${v.id} in box during walk`);
        }
      }
    });
    let crossed = 0;
    for (const v of seen.values()) {
      if (v.crossedOn !== undefined) {
        crossed++;
        assert.ok(['green', 'amber'].includes(v.crossedOn), `vehicle ${v.id} crossed on ${v.crossedOn}`);
      }
    }
    assert.ok(crossed > 500);
    assert.ok(sim.stats.pedestrianPhases > 5);
  });
}

test('signal follows the UK sequence red -> red+amber -> green -> amber -> red', () => {
  const sim = new Simulation({ seed: 9, controller: 'fixed' });
  const allowed = {
    NS_GREEN: ['NS_AMBER'],
    EW_GREEN: ['EW_AMBER'],
    NS_AMBER: ['ALL_RED'],
    EW_AMBER: ['ALL_RED'],
    ALL_RED: ['NS_RED_AMBER', 'EW_RED_AMBER', 'PED_WALK'],
    NS_RED_AMBER: ['NS_GREEN', 'ALL_RED'],
    EW_RED_AMBER: ['EW_GREEN', 'ALL_RED'],
    PED_WALK: ['PED_FLASH'],
    PED_FLASH: ['ALL_RED'],
  };
  const lights = { N: ['red'], E: ['red'] };
  lights.N[0] = sim.lightFor('N');
  lights.E[0] = sim.lightFor('E');
  let prev = sim.signal.phase;
  let prevStart = 0;
  for (let i = 0; i < 6000; i++) {
    sim.step(0.1);
    if (i === 2000) sim.requestPedestrian();
    const phase = sim.signal.phase;
    if (phase !== prev) {
      assert.ok(allowed[prev].includes(phase), `${prev} -> ${phase} not allowed`);
      const lasted = sim.time - prevStart;
      if (prev.endsWith('_AMBER') && !prev.endsWith('RED_AMBER')) assert.ok(Math.abs(lasted - 3) < 0.15, `amber lasted ${lasted}`);
      if (prev.endsWith('_RED_AMBER')) assert.ok(Math.abs(lasted - 2) < 0.15, `red+amber lasted ${lasted}`);
      prev = phase;
      prevStart = sim.time;
    }
    for (const a of ['N', 'E']) {
      const l = sim.lightFor(a);
      if (lights[a].at(-1) !== l) lights[a].push(l);
    }
  }
  const order = ['red', 'red_amber', 'green', 'amber'];
  for (const a of ['N', 'E']) {
    const seq = lights[a];
    assert.ok(seq.length > 20);
    for (let i = 1; i < seq.length; i++) {
      const expected = order[(order.indexOf(seq[i - 1]) + 1) % 4];
      assert.equal(seq[i], expected, `${a}: ${seq[i - 1]} -> ${seq[i]}`);
    }
  }
  // Opposing axes are never green/amber/red+amber at the same time.
  const s2 = new Simulation({ seed: 2, controller: 'actuated' });
  run(s2, 900, 0.1, (s) => {
    const ns = s.lightFor('N');
    const ew = s.lightFor('E');
    assert.ok(ns === 'red' || ew === 'red', `conflict ${ns}/${ew}`);
    assert.equal(s.lightFor('N'), s.lightFor('S'));
    assert.equal(s.lightFor('E'), s.lightFor('W'));
  });
});

test('pedestrian button leads to an all-red walk then flashing phase', () => {
  const sim = new Simulation({ seed: 4, controller: 'actuated' });
  run(sim, 20, 0.1);
  assert.equal(sim.pedestrianState(), 'dont_walk');
  assert.equal(sim.requestPedestrian(), true);
  assert.equal(sim.signal.ped, true);
  const t0 = sim.time;
  while (sim.signal.phase !== 'PED_WALK') {
    sim.step(0.1);
    assert.ok(sim.time - t0 < 15, 'walk phase served within 15 s');
  }
  assert.equal(sim.pedestrianState(), 'walk');
  assert.equal(sim.signal.ped, false);
  for (const a of APPROACHES) assert.equal(sim.lightFor(a), 'red');
  run(sim, 2, 0.1);
  assert.ok(sim.pedestrians.length >= 0);
  for (const p of sim.pedestrians) {
    assert.ok(Math.abs(p.x) <= BOX / 2 + 1e-9 && Math.abs(p.y) <= BOX / 2 + 1e-9);
    assert.ok(p.progress >= 0 && p.progress <= 1);
  }
  while (sim.signal.phase === 'PED_WALK') sim.step(0.1);
  assert.equal(sim.pedestrianState(), 'flashing');
  while (sim.signal.phase === 'PED_FLASH') sim.step(0.1);
  assert.equal(sim.pedestrianState(), 'dont_walk');
  assert.equal(sim.pedestrians.length, 0, 'everyone has finished crossing');
  assert.equal(sim.stats.pedestrianPhases, 1);
});

test('emergency pre-emption gives the emergency approach green within 10 s', () => {
  for (const seed of [1, 2, 3, 4, 5, 6]) {
    for (const approach of APPROACHES) {
      const sim = new Simulation({ seed, controller: 'fixed', demand: { N: 0.2, S: 0.2, E: 0.2, W: 0.2 } });
      run(sim, 17 + seed * 7.3, 0.1);
      if (seed % 2) sim.requestPedestrian();
      run(sim, seed * 1.7, 0.1);
      const t0 = sim.time;
      sim.spawnEmergency(approach);
      while (sim.lightFor(approach) !== 'green') {
        sim.step(0.1);
        assert.ok(sim.time - t0 <= 10, `seed ${seed} ${approach}: green after ${(sim.time - t0).toFixed(1)} s (phase ${sim.signal.phase})`);
      }
      // ...and it is held green until the emergency vehicle has crossed.
      let crossed = false;
      for (let i = 0; i < 1200 && !crossed; i++) {
        sim.step(0.1);
        const ev = sim.vehicles.find((v) => v.emergency);
        crossed = !ev || ev.pos >= STOP_LINE;
        if (!crossed) assert.equal(sim.lightFor(approach), 'green');
      }
      assert.ok(crossed, 'emergency vehicle crossed the junction');
      run(sim, 60, 0.5);
      assert.equal(sim.stats.emergencyServed, 1);
      assert.equal(AXIS_OF[approach], approach === 'N' || approach === 'S' ? 'NS' : 'EW');
    }
  }
});

test('setDemand(0) stops arrivals; reset clears state but keeps settings', () => {
  const sim = new Simulation({ seed: 8, controller: 'maxpressure' });
  for (const a of APPROACHES) sim.setDemand(a, 0);
  run(sim, 300);
  assert.equal(sim.stats.spawned, 0);
  assert.equal(sim.vehicles.length, 0);
  sim.setDemand('N', 0.3);
  run(sim, 120);
  assert.ok(sim.stats.spawned > 10);
  assert.ok(sim.vehicles.every((v) => v.approach === 'N'));
  sim.reset();
  assert.equal(sim.time, 0);
  assert.equal(sim.vehicles.length, 0);
  assert.equal(sim.stats.served, 0);
  assert.equal(sim.stats.history.length, 0);
  assert.equal(sim.controllerName, 'maxpressure');
  assert.equal(sim.demand.N, 0.3);
  assert.throws(() => sim.setDemand('X', 1));
});

test('history is sampled every 5 s and capped at 360 entries', () => {
  const sim = new Simulation({ seed: 1 });
  run(sim, 100, 1);
  assert.equal(sim.stats.history.length, 20);
  const h = sim.stats.history.at(-1);
  for (const k of ['t', 'avgQueue', 'throughputPerMin', 'avgWait']) assert.equal(typeof h[k], 'number');
  run(sim, 2000, 5);
  assert.equal(sim.stats.history.length, 360);
});

test('vehicle objects expose the fields the renderer needs', () => {
  const sim = new Simulation({ seed: 12, demand: HEAVY });
  run(sim, 60);
  assert.ok(sim.vehicles.length > 10);
  for (const v of sim.vehicles) {
    for (const k of ['id', 'approach', 'pos', 'speed', 'length', 'waitTime']) assert.equal(typeof v[k] === 'number' || typeof v[k] === 'string', true, k);
    assert.equal(typeof v.emergency, 'boolean');
    assert.equal(typeof v.braking, 'boolean');
    assert.match(v.color, /^#[0-9a-f]{6}$/i);
    assert.ok(v.pos <= PATH_LENGTH + v.length);
  }
  const s = sim.stats;
  for (const k of ['throughput', 'avgWait', 'maxWait', 'served', 'spawned', 'emergencyServed']) assert.equal(typeof s[k], 'number', k);
  for (const a of APPROACHES) assert.equal(typeof s.queue[a], 'number');
});
