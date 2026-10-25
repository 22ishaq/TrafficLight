import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runBenchmark, bestController } from '../js/sim/benchmark.js';

test('benchmark returns one averaged row per controller, quickly', () => {
  const t0 = performance.now();
  const rows = runBenchmark({ duration: 900, seeds: [1, 2, 3] });
  const ms = performance.now() - t0;
  assert.ok(ms < 3000, `took ${ms.toFixed(0)} ms`);
  assert.deepEqual(rows.map((r) => r.controller), ['fixed', 'actuated', 'maxpressure']);
  for (const r of rows) {
    for (const k of ['avgWait', 'maxWait', 'throughputPerHour', 'avgQueue']) {
      assert.ok(Number.isFinite(r[k]) && r[k] >= 0, `${r.controller}.${k} = ${r[k]}`);
    }
    assert.ok(r.throughputPerHour > 800);
  }
});

test('adaptive controllers beat fixed time on asymmetric demand', () => {
  const rows = runBenchmark({ demand: { N: 0.18, S: 0.18, E: 0.04, W: 0.04 }, seeds: [1, 2, 3] });
  const by = Object.fromEntries(rows.map((r) => [r.controller, r]));
  assert.ok(by.actuated.avgWait < by.fixed.avgWait, `actuated ${by.actuated.avgWait} vs fixed ${by.fixed.avgWait}`);
  assert.ok(by.maxpressure.avgWait < by.fixed.avgWait, `maxpressure ${by.maxpressure.avgWait} vs fixed ${by.fixed.avgWait}`);
  assert.notEqual(bestController(rows), 'fixed');
});

test('benchmark is deterministic', () => {
  const opts = { duration: 300, seeds: [4] };
  assert.deepEqual(runBenchmark(opts), runBenchmark(opts));
});

test('max-pressure stays efficient when every road is busy', () => {
  const rows = runBenchmark({ demand: { N: 0.2, S: 0.2, E: 0.2, W: 0.2 }, seeds: [1, 2] });
  const by = Object.fromEntries(rows.map((r) => [r.controller, r]));
  assert.ok(by.maxpressure.throughputPerHour > 0.9 * by.fixed.throughputPerHour,
    `maxpressure ${by.maxpressure.throughputPerHour} vs fixed ${by.fixed.throughputPerHour}`);
});

test('arrivals blocked off-road count towards waiting time', () => {
  const rows = runBenchmark({ controllers: ['fixed'], demand: { N: 0.6, S: 0, E: 0, W: 0 }, seeds: [1], duration: 600 });
  assert.ok(rows[0].maxWait > 120, `maxWait ${rows[0].maxWait}`);
});
