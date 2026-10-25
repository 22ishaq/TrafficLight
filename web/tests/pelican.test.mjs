// Cross-language parity: replay the golden trace generated from greenwave/pelican.py
// (tools/gen_pelican_trace.py) against the browser port in js/classic.js.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PelicanCrossing, DEFAULT_TIMINGS, FAST_TIMINGS } from '../js/classic.js';

const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/pelican_trace.json', import.meta.url), 'utf8'));
const round = (x) => (x === null ? null : Number(x.toFixed(fixture.decimals)));

function snapshot(c) {
  return {
    time: round(c.time),
    phase: c.phase,
    phase_time: round(c.phaseTime),
    remaining: round(c.remaining),
    vehicle: c.vehicleSignal,
    pedestrian: c.pedestrianSignal,
    wait: c.waitIndicator,
    served: c.crossingsServed,
    vehicle_lamps: c.vehicleLamps,
    pedestrian_lamps: { red_man: c.pedestrianLamps.redMan, green_man: c.pedestrianLamps.greenMan },
  };
}

test('fixture has scenarios for both timing sets', () => {
  assert.ok(fixture.scenarios.length >= 4);
  assert.deepEqual(new Set(fixture.scenarios.map((s) => s.timings)), new Set(['default', 'fast']));
});

for (const scenario of fixture.scenarios) {
  test(`JS pelican matches Python trace: ${scenario.name}`, () => {
    const crossing = new PelicanCrossing(scenario.timings === 'fast' ? FAST_TIMINGS : DEFAULT_TIMINGS);
    const trace = [{ action: 'start', ...snapshot(crossing) }];
    for (const step of scenario.steps) {
      let record;
      if (step[0] === 'press') record = { action: 'press', accepted: crossing.pressButton() };
      else record = { action: 'tick', dt: step[1], entered: crossing.tick(step[1]) };
      trace.push({ ...record, ...snapshot(crossing) });
    }
    assert.equal(trace.length, scenario.trace.length);
    for (let i = 0; i < trace.length; i++) {
      assert.deepEqual(trace[i], scenario.trace[i], `${scenario.name}: step ${i} (${JSON.stringify(scenario.steps[i - 1] ?? 'start')})`);
    }
  });
}
