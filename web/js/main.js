// GreenWave UI: wires the controls and stats panel to the simulation engine and runs the animation loop.
import { Simulation, APPROACHES, DEFAULT_DEMAND } from './sim/engine.js';
import { runBenchmark } from './sim/benchmark.js';
import { Rng } from './sim/rng.js';
import { JunctionRenderer } from './render.js';
import { LineChart, SignalTimeline, clock } from './charts.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

// ---------- theme ----------
const root = document.documentElement;
function storedTheme() {
  try { return localStorage.getItem('greenwave-theme'); } catch { return null; }
}
const initialTheme = params.get('theme') || storedTheme();
if (initialTheme === 'light' || initialTheme === 'dark') root.dataset.theme = initialTheme;

function effectiveTheme() {
  if (root.dataset.theme) return root.dataset.theme;
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// ---------- state ----------
const CONTROLLERS = ['fixed', 'actuated', 'maxpressure', 'manual'];
const CONTROLLER_LABEL = { fixed: 'Fixed-time', actuated: 'Actuated', maxpressure: 'Max-pressure', manual: 'Manual' };
const sim = new Simulation({ seed: Number(params.get('seed')) || 42, controller: 'actuated' });
let speed = 1;
let lastSpeed = 1;

const renderer = new JunctionRenderer($('junction'));
const chart = new LineChart($('chart'), [
  { key: 'avgQueue', colorVar: '--chart-queue', color: '#2563eb', axis: 'left', fill: true },
  { key: 'avgWait', colorVar: '--chart-wait', color: '#ea580c', axis: 'right' },
]);
const tlNS = new SignalTimeline($('tlNS'));
const tlEW = new SignalTimeline($('tlEW'));

// ---------- controls ----------
const controllerSel = $('controllerSel');
function setController(name) {
  if (!CONTROLLERS.includes(name)) return;
  sim.setController(name);
  controllerSel.value = name;
  $('controllerLabel').textContent = `${CONTROLLER_LABEL[name]} control`;
  $('manualBtn').disabled = name !== 'manual';
}
controllerSel.addEventListener('change', () => setController(controllerSel.value));

const speedButtons = [...document.querySelectorAll('#speedGroup button')];
function setSpeed(v) {
  speed = v;
  if (v > 0) lastSpeed = v;
  for (const b of speedButtons) b.setAttribute('aria-checked', String(Number(b.dataset.speed) === v));
}
for (const b of speedButtons) b.addEventListener('click', () => setSpeed(Number(b.dataset.speed)));

// demand sliders (UI in vehicles/minute, engine in vehicles/second)
const DIR_NAME = { N: 'North', E: 'East', S: 'South', W: 'West' };
const sliders = $('sliders');
const outputs = {};
const sliderCtl = {};
for (const a of APPROACHES) {
  const row = document.createElement('div');
  row.className = 'slider-row';
  const id = `demand${a}`;
  row.innerHTML = `<label class="dir" for="${id}" title="${DIR_NAME[a]} approach">${a}</label>
    <input type="range" id="${id}" min="0" max="30" step="0.5" aria-label="${DIR_NAME[a]} approach demand, vehicles per minute">
    <output for="${id}"></output>`;
  const input = row.querySelector('input');
  const out = row.querySelector('output');
  input.value = String(Math.round((sim.demand[a] ?? 0) * 60 * 2) / 2);
  const paint = () => {
    out.textContent = Number(input.value).toFixed(1);
    input.style.setProperty('--fill', `${(Number(input.value) / Number(input.max)) * 100}%`);
  };
  paint();
  input.addEventListener('input', () => {
    paint();
    sim.setDemand(a, Number(input.value) / 60);
    $('scenarioSel').value = 'custom';
  });
  sliderCtl[a] = { input, paint };
  outputs[a] = out;
  sliders.append(row);
}

// scenario presets (vehicles/minute, like the sliders); null = engine defaults
const SCENARIOS = {
  balanced: null,
  morning: { N: 14, S: 13, E: 3, W: 3.5 },
  stadium: { N: 3, S: 3.5, E: 15, W: 14 },
  night: { N: 1.5, S: 1.5, E: 1, W: 1 },
  gridlock: { N: 12.5, S: 12.5, E: 11.5, W: 11.5 },
};
function applyScenario(name) {
  if (!(name in SCENARIOS)) return;
  const preset = SCENARIOS[name];
  for (const a of APPROACHES) {
    const perSec = preset ? preset[a] / 60 : DEFAULT_DEMAND[a];
    sim.setDemand(a, perSec);
    sliderCtl[a].input.value = String(Math.round(perSec * 60 * 2) / 2);
    sliderCtl[a].paint();
  }
  $('scenarioSel').value = name;
  if (name === 'night' && effectiveTheme() !== 'dark') toggleTheme();
}
$('scenarioSel').addEventListener('change', (e) => applyScenario(e.target.value));

// queue bars
const queueEls = {};
for (const a of APPROACHES) {
  const row = document.createElement('div');
  row.className = 'q-row';
  row.innerHTML = `<span class="dir" title="${DIR_NAME[a]} approach">${a}</span><div class="q-bar"><div class="q-fill"></div></div><output>0</output>`;
  queueEls[a] = { fill: row.querySelector('.q-fill'), out: row.querySelector('output') };
  $('queues').append(row);
}

function pressPedestrian() {
  sim.requestPedestrian();
  $('waitLamp').classList.add('on');
}
// UI-side randomness (emergency approach) gets its own seeded stream so seeded runs reproduce
// without disturbing the simulation's traffic stream.
let uiRng = new Rng(sim.seed ^ 0x9e3779b9);
function sendEmergency() {
  sim.spawnEmergency(uiRng.pick(APPROACHES));
}
function manualSwitch() {
  if (sim.manualSwitch()) return;
  // Rejected (not in manual mode, or not during a green phase): shake and explain briefly.
  const btn = $('manualBtn');
  btn.animate?.([{ transform: 'translateX(0)' }, { transform: 'translateX(-5px)' }, { transform: 'translateX(5px)' },
    { transform: 'translateX(-3px)' }, { transform: 'translateX(0)' }], { duration: 320 });
  if (!btn.dataset.label) btn.dataset.label = btn.textContent;
  btn.textContent = sim.controllerName === 'manual' ? 'Wait for green…' : 'Manual mode only';
  clearTimeout(btn._hintTimer);
  btn._hintTimer = setTimeout(() => { btn.textContent = btn.dataset.label; }, 1200);
}
function resetSim() {
  sim.reset(Math.floor(Math.random() * 1e9));
  uiRng = new Rng(sim.seed ^ 0x9e3779b9);
  tlNS.reset(); tlEW.reset();
  lastEventKey = '';
  updatePanel(true);
}
function toggleTheme() {
  const next = effectiveTheme() === 'dark' ? 'light' : 'dark';
  root.dataset.theme = next;
  try { localStorage.setItem('greenwave-theme', next); } catch { /* storage unavailable */ }
  renderer.readTheme();
  updatePanel(true);
}

$('pedBtn').addEventListener('click', pressPedestrian);
$('emergencyBtn').addEventListener('click', sendEmergency);
$('manualBtn').addEventListener('click', manualSwitch);
$('resetBtn').addEventListener('click', resetSim);
$('themeBtn').addEventListener('click', toggleTheme);
matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => renderer.readTheme());

document.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const tag = e.target?.tagName;
  const isRange = tag === 'INPUT' && e.target.type === 'range';
  if ((tag === 'INPUT' && !isRange) || tag === 'SELECT' || tag === 'TEXTAREA') return;
  if (isRange && e.key.startsWith('Arrow')) return; // arrows belong to the slider
  const k = e.key.toLowerCase();
  if (k === ' ') { e.preventDefault(); setSpeed(speed > 0 ? 0 : lastSpeed); }
  else if (k >= '1' && k <= '4') setController(CONTROLLERS[Number(k) - 1]);
  else if (k === 'p') pressPedestrian();
  else if (k === 'e') sendEmergency();
  else if (k === 'm') manualSwitch();
  else if (k === 'r') resetSim();
  else if (k === 't') toggleTheme();
});

// ---------- benchmark ----------
const benchBtn = $('benchBtn');
benchBtn.addEventListener('click', () => {
  benchBtn.disabled = true;
  const out = $('benchResult');
  const demand = { ...sim.demand };
  const list = ['fixed', 'actuated', 'maxpressure'];
  const results = [];
  out.innerHTML = '<p class="muted small"><span class="spinner"></span>Running…</p>';
  const next = () => {
    const c = list[results.length];
    out.innerHTML = `<p class="muted small"><span class="spinner"></span>Simulating ${CONTROLLER_LABEL[c]}… (${results.length + 1}/${list.length})</p>`;
    setTimeout(() => {
      try {
        results.push(...runBenchmark({ controllers: [c], duration: 900, seeds: [1, 2, 3], demand }));
      } catch (err) {
        out.innerHTML = `<p class="small" style="color:var(--danger)">Benchmark failed: ${escapeHtml(err.message)}</p>`;
        benchBtn.disabled = false;
        return;
      }
      if (results.length < list.length) next();
      else { renderBench(results); benchBtn.disabled = false; }
    }, 20);
  };
  next();
});

function renderBench(results) {
  const best = results.reduce((b, r) => (r.avgWait < b.avgWait ? r : b), results[0]);
  const worst = Math.max(...results.map((r) => r.avgWait), 1e-9);
  const rows = results.map((r) => `
    <tr class="${r === best ? 'best' : ''}">
      <td>${CONTROLLER_LABEL[r.controller] || r.controller}<div class="bench-bar" style="width:${Math.max(4, (r.avgWait / worst) * 100).toFixed(0)}%"></div></td>
      <td>${r.avgWait.toFixed(1)}s</td>
      <td>${r.maxWait.toFixed(0)}s</td>
      <td>${Math.round(r.throughputPerHour)}</td>
      <td>${r.avgQueue.toFixed(1)}</td>
    </tr>`).join('');
  const others = results.filter((r) => r !== best);
  const worstR = others.reduce((w, r) => (r.avgWait > w.avgWait ? r : w), others[0] || best);
  const gain = worstR && worstR.avgWait > 0 ? Math.round((1 - best.avgWait / worstR.avgWait) * 100) : 0;
  $('benchResult').innerHTML = `
    <table class="bench-table">
      <thead><tr><th>Controller</th><th>Avg wait</th><th>Max</th><th>Veh/h</th><th>Queue</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="small muted">${CONTROLLER_LABEL[best.controller]} wins — ${gain}% less waiting than ${CONTROLLER_LABEL[worstR.controller]}.</p>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------- live panel ----------
const PHASE_LABEL = {
  NS_GREEN: 'N/S green', EW_GREEN: 'E/W green',
  NS_AMBER: 'N/S amber', EW_AMBER: 'E/W amber',
  NS_RED_AMBER: 'N/S red + amber', EW_RED_AMBER: 'E/W red + amber',
  ALL_RED: 'All red', PED_WALK: 'Pedestrians: walk', PED_FLASH: 'Pedestrians: clear',
};
const PHASE_COLOUR = {
  GREEN: 'var(--lamp-green)', AMBER: 'var(--lamp-amber)', RED_AMBER: 'var(--lamp-amber)',
  ALL_RED: 'var(--lamp-red)', PED_WALK: 'var(--lamp-green)', PED_FLASH: 'var(--lamp-amber)',
};
let lastEventKey = '';

function phaseColour(phase) {
  if (PHASE_COLOUR[phase]) return PHASE_COLOUR[phase];
  if (phase.endsWith('RED_AMBER')) return PHASE_COLOUR.RED_AMBER;
  if (phase.endsWith('GREEN')) return PHASE_COLOUR.GREEN;
  if (phase.endsWith('AMBER')) return PHASE_COLOUR.AMBER;
  return 'var(--lamp-red)';
}

function setTile(id, value, unit) {
  $(id).innerHTML = unit ? `${value}<small>${unit}</small>` : value;
}

function updatePanel() {
  const st = sim.stats;
  const sig = sim.signal;
  $('simClock').textContent = clock(sim.time);
  $('phaseName').textContent = PHASE_LABEL[sig.phase] || sig.phase;
  $('phaseTime').textContent = `${(sig.phaseTime || 0).toFixed(1)} s`;
  const dot = $('phaseDot');
  const col = phaseColour(sig.phase);
  dot.style.background = col;
  dot.style.boxShadow = `0 0 10px ${col}`;

  setTile('statAvgWait', (st.avgWait || 0).toFixed(1), 's');
  setTile('statThroughput', (st.throughputPerMin || 0).toFixed(1), '/min');
  setTile('statMaxWait', Math.round(st.maxWait || 0), 's');
  setTile('statServed', String(st.served || 0));

  for (const a of APPROACHES) {
    const q = st.queue?.[a] || 0;
    const el = queueEls[a];
    el.out.textContent = q;
    el.fill.style.width = `${Math.min(100, (q / 20) * 100)}%`;
    el.fill.style.backgroundColor = q < 6 ? 'var(--lamp-green)' : q < 12 ? 'var(--lamp-amber)' : 'var(--lamp-red)';
  }

  const ped = sim.pedestrianState();
  $('waitLamp').classList.toggle('on', !!sig.ped && ped === 'dont_walk');
  const toast = $('pedToast');
  toast.hidden = ped === 'dont_walk';
  toast.textContent = ped === 'walk' ? 'Green man — pedestrians crossing' : 'Crossing closing';

  $('emergencyBtn').querySelector('.siren').classList.toggle('on', !!sim.signal.preempt || sim.vehicles.some((v) => v.emergency));

  // event log (newest first)
  const ev = sim.events || [];
  const key = ev.length ? `${ev.length}:${ev[ev.length - 1].t}` : '';
  if (key !== lastEventKey) {
    lastEventKey = key;
    $('events').innerHTML = ev.slice(-4).reverse().map((e) =>
      `<li data-type="${escapeHtml(e.type)}"><time>${clock(e.t)}</time><i></i><span>${escapeHtml(e.message)}</span></li>`).join('');
  }

  chart.draw(st.history || []);
}

// ---------- main loop ----------
const wrap = $('canvasWrap');
new ResizeObserver(() => { renderer.resize(); renderer.draw(sim, performance.now() / 1000); }).observe(wrap);

if (params.get('scenario')) applyScenario(params.get('scenario'));
// Clamp URL params so a hand-edited link can't freeze the tab.
const clampParam = (v, lo, hi) => (Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : 0);
const warmup = clampParam(Number(params.get('warmup')), 0, 3600);
if (warmup > 0) sim.step(warmup);
if (params.get('speed')) setSpeed(clampParam(Number(params.get('speed')), 0, 16));
setController(sim.controllerName || 'actuated');

let last = performance.now();
let lastPanel = 0;
let lastSample = -1;
function frame(now) {
  const dtReal = Math.min(0.1, Math.max(0, (now - last) / 1000));
  last = now;
  if (speed > 0 && dtReal > 0) sim.step(dtReal * speed);

  if (sim.time - lastSample >= 0.25 || sim.time < lastSample) {
    lastSample = sim.time;
    tlNS.push(sim.time, sim.lightFor('N'));
    tlEW.push(sim.time, sim.lightFor('E'));
  }

  renderer.draw(sim, now / 1000);
  if (now - lastPanel > 200) {
    lastPanel = now;
    updatePanel();
    tlNS.draw(sim.time);
    tlEW.draw(sim.time);
  }
  requestAnimationFrame(frame);
}
updatePanel();
requestAnimationFrame(frame);

// handy for debugging from the console
window.greenwave = { sim, setController, setSpeed };
