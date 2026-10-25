// GreenWave classic mode: a UK pelican crossing in the browser.
// PelicanCrossing is a faithful port of greenwave/pelican.py (same phases, timings and edge cases).

const EPSILON = 1e-9;

export const PelicanPhase = Object.freeze({
  VEHICLE_GREEN: 'VEHICLE_GREEN',
  VEHICLE_AMBER: 'VEHICLE_AMBER',
  ALL_RED: 'ALL_RED',
  PEDESTRIAN_WALK: 'PEDESTRIAN_WALK',
  FLASHING: 'FLASHING',
});

export const DEFAULT_TIMINGS = Object.freeze({ minGreen: 10, amber: 3, allRed: 2, walk: 7, flashing: 6, flashPeriod: 1 });
export const FAST_TIMINGS = Object.freeze({ minGreen: 3, amber: 1.5, allRed: 1, walk: 3, flashing: 3, flashPeriod: 0.5 });

const NEXT = {
  VEHICLE_GREEN: 'VEHICLE_AMBER',
  VEHICLE_AMBER: 'ALL_RED',
  ALL_RED: 'PEDESTRIAN_WALK',
  PEDESTRIAN_WALK: 'FLASHING',
  FLASHING: 'VEHICLE_GREEN',
};

export class PelicanCrossing {
  constructor(timings = DEFAULT_TIMINGS) {
    for (const k of ['amber', 'allRed', 'walk', 'flashing', 'flashPeriod']) {
      if (!(timings[k] > 0)) throw new Error(`${k} must be positive`);
    }
    if (timings.minGreen < 0) throw new Error('minGreen must be non-negative');
    this.timings = { ...timings };
    this.reset();
  }

  /** Register a pedestrian request; ignored while the green man already shows. */
  pressButton() {
    if (this.phase === PelicanPhase.PEDESTRIAN_WALK) return false;
    if (!this._demand) {
      this._demand = true;
      this._demandAt = this.phase === PelicanPhase.VEHICLE_GREEN ? this.phaseTime : 0;
    }
    return true;
  }

  /** Advance by dt seconds; surplus time carries into following phases. Returns phases entered. */
  tick(dt) {
    if (dt < 0) throw new Error('dt must be non-negative');
    this.time += dt;
    this.phaseTime += dt;
    const entered = [];
    for (;;) {
      const endsAt = this._phaseEnd();
      if (endsAt === null || this.phaseTime < endsAt - EPSILON) break;
      const overflow = Math.max(0, this.phaseTime - endsAt);
      this._enter(NEXT[this.phase]);
      this.phaseTime = overflow;
      entered.push(this.phase);
    }
    return entered;
  }

  _phaseEnd() {
    const t = this.timings;
    switch (this.phase) {
      case PelicanPhase.VEHICLE_GREEN: return this._demand ? Math.max(t.minGreen, this._demandAt) : null;
      case PelicanPhase.VEHICLE_AMBER: return t.amber;
      case PelicanPhase.ALL_RED: return t.allRed;
      case PelicanPhase.PEDESTRIAN_WALK: return t.walk;
      default: return t.flashing;
    }
  }

  _enter(phase) {
    this.phase = phase;
    if (phase === PelicanPhase.PEDESTRIAN_WALK) {
      this._demand = false;
      this.crossingsServed += 1;
    } else if (phase === PelicanPhase.VEHICLE_GREEN && this._demand) {
      this._demandAt = 0; // press queued during flashing; min green counts from now
    }
  }

  reset() {
    this.phase = PelicanPhase.VEHICLE_GREEN;
    this.phaseTime = 0;
    this.time = 0;
    this.crossingsServed = 0;
    this._demand = false;
    this._demandAt = 0;
  }

  /** Seconds left in the current phase (null while resting on green). */
  get remaining() {
    const end = this._phaseEnd();
    return end === null ? null : Math.max(0, end - this.phaseTime);
  }
  get flashOn() {
    const p = this.timings.flashPeriod;
    return (this.phaseTime % p) < p / 2;
  }
  get vehicleSignal() {
    return { VEHICLE_GREEN: 'green', VEHICLE_AMBER: 'amber', ALL_RED: 'red', PEDESTRIAN_WALK: 'red', FLASHING: 'flashing_amber' }[this.phase];
  }
  get pedestrianSignal() {
    if (this.phase === PelicanPhase.PEDESTRIAN_WALK) return 'walk';
    if (this.phase === PelicanPhase.FLASHING) return 'flashing';
    return 'dont_walk';
  }
  get waitIndicator() { return this._demand; }
  get vehicleLamps() {
    const s = this.vehicleSignal;
    return { red: s === 'red', amber: s === 'amber' || (s === 'flashing_amber' && this.flashOn), green: s === 'green' };
  }
  get pedestrianLamps() {
    const s = this.pedestrianSignal;
    return { redMan: s === 'dont_walk', greenMan: s === 'walk' || (s === 'flashing' && this.flashOn) };
  }
  get vehiclesMayProceed() {
    return this.phase === PelicanPhase.VEHICLE_GREEN || this.phase === PelicanPhase.FLASHING;
  }
}

// ======================================================================= scene
// Logical scene units (scaled to fit the canvas). Road runs left-right; drive on the LEFT:
// eastbound traffic uses the top lane, westbound the bottom lane.
const SW = 1000, SH = 600;
const ROAD_TOP = 300, ROAD_BOT = 460, ROAD_MID = 380;
const XING_L = 468, XING_R = 532;             // crossing edges (studs)
const STOP_S = 432;                            // stop line, as distance along each lane's path
const CAR_LEN = 58, CAR_W = 30, V0 = 170, ACC = 140, BRAKE = 300, COMFORT = 220, MIN_GAP = 16;
const WAIT_Y = { top: ROAD_TOP - 18, bottom: ROAD_BOT + 18 };
const BUTTON_BOX = { x: 700, y: 132, w: 64, h: 112 };

const CAR_COLOURS = ['#e11d48', '#2563eb', '#f8fafc', '#0f172a', '#64748b', '#0891b2', '#16a34a', '#f97316', '#7c3aed', '#ca8a04'];
const PED_COLOURS = ['#f43f5e', '#0ea5e9', '#a855f7', '#f59e0b', '#10b981', '#e2e8f0'];

if (typeof document !== 'undefined') startApp();

function startApp() {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const params = new URLSearchParams(location.search);
  try {
    const t = params.get('theme') || localStorage.getItem('greenwave-theme');
    if (t === 'light' || t === 'dark') root.dataset.theme = t;
  } catch { /* storage unavailable */ }

  let crossing = new PelicanCrossing(DEFAULT_TIMINGS);
  const canvas = $('crossing');
  const ctx = canvas.getContext('2d');
  let theme = readTheme();
  let view = { w: 1, h: 1, dpr: 1, k: 1, ox: 0, oy: 0 };

  // ---------------------------------------------------------------- traffic
  let nextId = 1;
  let carsPassed = 0;
  const cars = { E: [], W: [] };              // front-most first
  const nextSpawn = { E: 0.5, W: 1.8 };
  const peds = [];

  const carX = (lane, s) => (lane === 'E' ? s : SW - s);
  const laneY = (lane) => (lane === 'E' ? (ROAD_TOP + ROAD_MID) / 2 : (ROAD_MID + ROAD_BOT) / 2);
  const crossingOccupied = () => peds.some((p) => p.state === 'crossing');

  function spawnCar(lane) {
    const list = cars[lane];
    const last = list[list.length - 1];
    if (last && last.s - CAR_LEN < MIN_GAP + 4) return false;
    list.push({ id: nextId++, s: -10, v: V0 * 0.9, braking: false, colour: CAR_COLOURS[Math.floor(Math.random() * CAR_COLOURS.length)], counted: false });
    return true;
  }

  function mustStop(car) {
    if (car.s > STOP_S + 1) return false;                // already over the line: keep going
    const sig = crossing.vehicleSignal;
    if (sig === 'green') return false;
    if (sig === 'flashing_amber') return crossingOccupied();
    const d = STOP_S - car.s;
    if (sig === 'amber') return d > (car.v * car.v) / (2 * COMFORT); // stop only if it can do so comfortably
    return true;                                         // red
  }

  function stepCars(dt) {
    for (const lane of ['E', 'W']) {
      nextSpawn[lane] -= dt;
      if (nextSpawn[lane] <= 0) {
        if (spawnCar(lane)) nextSpawn[lane] = 1.2 + Math.random() * 3.2;
        else nextSpawn[lane] = 0.3;
      }
      const list = cars[lane];
      for (let i = 0; i < list.length; i++) {
        const c = list[i];
        let gap = Infinity;
        if (i > 0) gap = list[i - 1].s - CAR_LEN - c.s - MIN_GAP;
        if (mustStop(c)) gap = Math.min(gap, STOP_S - c.s - 2);
        const vAllowed = Math.sqrt(Math.max(0, 2 * BRAKE * Math.max(0, gap)));
        const vNew = Math.max(0, Math.min(c.v + ACC * dt, V0, vAllowed));
        c.braking = vNew < c.v - 0.5 || (vNew < 5 && gap < 40);
        c.v = vNew;
        c.s += c.v * dt;
        if (!c.counted && c.s > SW / 2) { c.counted = true; carsPassed++; }
      }
      while (list.length && list[0].s > SW + CAR_LEN + 20) list.shift();
    }
  }

  // ------------------------------------------------------------- pedestrians
  function addPed(side) {
    const waiting = peds.filter((p) => p.side === side && p.state === 'waiting').length;
    if (waiting >= 4) return;
    const x = XING_L + 10 + waiting * 15 + Math.random() * 3;
    peds.push({ id: nextId++, side, x, y: WAIT_Y[side] + (Math.random() - 0.5) * 8, state: 'waiting', delay: 0, speed: 46 + Math.random() * 18, colour: PED_COLOURS[Math.floor(Math.random() * PED_COLOURS.length)], walkT: 0 });
  }

  function stepPeds(dt) {
    const sig = crossing.pedestrianSignal;
    for (const p of peds) {
      p.walkT += dt;
      if (p.state === 'waiting' && sig === 'walk') {
        p.delay -= dt;
        if (p.delay <= 0) p.state = 'crossing';
      }
      if (p.state === 'crossing') {
        const target = p.side === 'top' ? WAIT_Y.bottom + 6 : WAIT_Y.top - 6;
        const dir = Math.sign(target - p.y);
        p.y += dir * p.speed * dt;
        if ((dir > 0 && p.y >= target) || (dir < 0 && p.y <= target)) { p.y = target; p.state = 'leaving'; p.dirX = p.side === 'top' ? 1 : -1; }
      } else if (p.state === 'leaving') {
        p.x += p.dirX * p.speed * 0.8 * dt;
      }
    }
    for (let i = peds.length - 1; i >= 0; i--) if (peds[i].x < -30 || peds[i].x > SW + 30) peds.splice(i, 1);
  }

  // ------------------------------------------------------------------ input
  function press() {
    const accepted = crossing.pressButton();
    if (accepted) {
      const n = 1 + Math.floor(Math.random() * 2);
      for (let i = 0; i < n; i++) addPed(Math.random() < 0.5 ? 'top' : 'bottom');
      for (const p of peds) if (p.state === 'waiting') p.delay = Math.random() * 1.2;
    }
    pulse = 1;
    updatePanel();
  }
  let pulse = 0;

  function setFast(on) {
    // keep the current phase; swap timings in place like a re-configured controller
    crossing.timings = { ...(on ? FAST_TIMINGS : DEFAULT_TIMINGS) };
    $('fastChk').checked = on;
    renderSequenceTimes();
  }

  $('pushBtn').addEventListener('click', press);
  $('fastChk').addEventListener('change', (e) => setFast(e.target.checked));
  $('themeBtn').addEventListener('click', toggleTheme);
  canvas.addEventListener('click', (e) => {
    const r = canvas.getBoundingClientRect();
    const x = (e.clientX - r.left - view.ox) / view.k, y = (e.clientY - r.top - view.oy) / view.k;
    const b = BUTTON_BOX;
    if (x >= b.x - 8 && x <= b.x + b.w + 8 && y >= b.y - 8 && y <= b.y + b.h + 8) press();
  });
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = e.target?.tagName;
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); press(); }
    else if (k === 'f') setFast(!$('fastChk').checked);
    else if (k === 't') toggleTheme();
  });

  function toggleTheme() {
    const cur = root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const next = cur === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem('greenwave-theme', next); } catch { /* storage unavailable */ }
    theme = readTheme();
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => { theme = readTheme(); });

  // ------------------------------------------------------------------ panel
  const LABEL = {
    VEHICLE_GREEN: 'Traffic green',
    VEHICLE_AMBER: 'Steady amber',
    ALL_RED: 'All red',
    PEDESTRIAN_WALK: 'Green man — cross now',
    FLASHING: 'Flashing amber',
  };
  const HINT = {
    VEHICLE_GREEN: 'Press the button (or Space) to cross',
    VEHICLE_AMBER: 'Traffic stopping',
    ALL_RED: 'Clearing the crossing',
    PEDESTRIAN_WALK: 'Pedestrians crossing',
    FLASHING: 'Finish crossing · drivers give way',
  };
  const DOT = { VEHICLE_GREEN: '--lamp-green', VEHICLE_AMBER: '--lamp-amber', ALL_RED: '--lamp-red', PEDESTRIAN_WALK: '--lamp-green', FLASHING: '--lamp-amber' };

  function renderSequenceTimes() {
    const t = crossing.timings;
    const val = { VEHICLE_GREEN: `≥ ${t.minGreen}s`, VEHICLE_AMBER: `${t.amber}s`, ALL_RED: `${t.allRed}s`, PEDESTRIAN_WALK: `${t.walk}s`, FLASHING: `${t.flashing}s` };
    for (const li of document.querySelectorAll('#seq li')) li.querySelector('output').textContent = val[li.dataset.phase];
  }

  function updatePanel() {
    const ph = crossing.phase;
    $('phaseName').textContent = ph === 'VEHICLE_GREEN' && crossing.waitIndicator ? 'Traffic green · WAIT' : LABEL[ph];
    const rem = crossing.remaining;
    $('phaseCountdown').textContent = rem === null ? '' : `${rem.toFixed(1)} s`;
    $('phaseHint').textContent = HINT[ph];
    const dot = $('phaseDot');
    dot.style.background = `var(${DOT[ph]})`;
    dot.style.boxShadow = `0 0 10px var(${DOT[ph]})`;
    $('waitLamp').classList.toggle('on', crossing.waitIndicator);
    $('statCrossings').textContent = String(crossing.crossingsServed);
    $('statCars').textContent = String(carsPassed);
    for (const li of document.querySelectorAll('#seq li')) li.classList.toggle('active', li.dataset.phase === ph);
  }

  // ---------------------------------------------------------------- drawing
  function readTheme() {
    const st = getComputedStyle(root);
    const v = (n, f) => st.getPropertyValue(n).trim() || f;
    return {
      grass: v('--scene-grass', '#b9d7a8'), pavement: v('--scene-pavement', '#d9dde3'), kerb: v('--scene-kerb', '#9aa3ae'),
      road: v('--scene-road', '#4b5360'), marking: v('--scene-marking', '#f8fafc'), shadow: v('--scene-shadow', 'rgba(0,0,0,.25)'),
      lampOff: v('--lamp-off', '#2b3340'), night: parseFloat(v('--scene-night', '0')) > 0.5,
    };
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const r = canvas.getBoundingClientRect();
    const w = Math.max(200, Math.round(r.width)), h = Math.max(150, Math.round(r.height));
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const k = Math.min(w / SW, h / SH);
    view = { w, h, dpr, k, ox: (w - SW * k) / 2, oy: (h - SH * k) / 2 };
  }
  new ResizeObserver(resize).observe($('canvasWrap'));
  resize();

  function rr(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  function glow(x, y, r, colour, a = 0.6) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, hexA(colour, a)); g.addColorStop(1, hexA(colour, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function zigzag(x0, x1, y) {
    ctx.beginPath();
    const n = Math.round((x1 - x0) / 22);
    for (let i = 0; i <= n; i++) {
      const x = x0 + ((x1 - x0) * i) / n;
      const yy = y + (i % 2 ? -6 : 6);
      if (i === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
    }
    ctx.stroke();
  }

  function drawRoad() {
    const T = theme;
    ctx.fillStyle = T.grass; ctx.fillRect(-200, -200, SW + 400, SH + 400);
    ctx.fillStyle = T.pavement;
    ctx.fillRect(-200, ROAD_TOP - 70, SW + 400, 70);
    ctx.fillRect(-200, ROAD_BOT, SW + 400, 70);
    ctx.fillStyle = T.road; ctx.fillRect(-200, ROAD_TOP, SW + 400, ROAD_BOT - ROAD_TOP);
    ctx.fillStyle = T.kerb;
    ctx.fillRect(-200, ROAD_TOP - 3, SW + 400, 3);
    ctx.fillRect(-200, ROAD_BOT, SW + 400, 3);
    // tactile paving at the crossing
    ctx.fillStyle = T.night ? '#7a5a3a' : '#c98a6b';
    ctx.fillRect(XING_L, ROAD_TOP - 26, XING_R - XING_L, 23);
    ctx.fillRect(XING_L, ROAD_BOT + 3, XING_R - XING_L, 23);
    ctx.fillStyle = 'rgba(0,0,0,.18)';
    for (let x = XING_L + 5; x < XING_R; x += 8) for (const y0 of [ROAD_TOP - 23, ROAD_BOT + 6]) for (let y = y0; y < y0 + 18; y += 8) { ctx.beginPath(); ctx.arc(x, y + 2, 1.6, 0, Math.PI * 2); ctx.fill(); }

    ctx.strokeStyle = T.marking; ctx.fillStyle = T.marking;
    // centre line (broken), interrupted by the zig-zag zone
    for (let x = -200; x < SW + 200; x += 46) {
      if (x > 230 && x < 770) continue;
      ctx.fillRect(x, ROAD_MID - 2, 26, 4);
    }
    // zig-zags: kerbs and centre, both approaches
    ctx.lineWidth = 3;
    for (const [x0, x1] of [[240, STOP_S - 2], [SW - STOP_S + 2, 760]]) {
      zigzag(x0, x1, ROAD_TOP + 10);
      zigzag(x0, x1, ROAD_MID);
      zigzag(x0, x1, ROAD_BOT - 10);
    }
    // stop lines (each lane, before the crossing)
    ctx.fillRect(STOP_S - 5, ROAD_TOP + 2, 5, ROAD_MID - ROAD_TOP - 4);
    ctx.fillRect(SW - STOP_S, ROAD_MID + 2, 5, ROAD_BOT - ROAD_MID - 4);
    // pelican studs: two broken lines across the road, no zebra stripes
    for (const x of [XING_L, XING_R]) for (let y = ROAD_TOP + 4; y < ROAD_BOT - 4; y += 16) ctx.fillRect(x - 3, y, 6, 9);
  }

  function drawCar(lane, c, t) {
    const x = carX(lane, c.s), y = laneY(lane);
    ctx.save();
    ctx.translate(x, y);
    if (lane === 'W') ctx.rotate(Math.PI);
    if (theme.night) {
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      const g = ctx.createLinearGradient(0, 0, 150, 0);
      g.addColorStop(0, 'rgba(255,244,200,.35)'); g.addColorStop(1, 'rgba(255,244,200,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(0, -8); ctx.lineTo(150, -34); ctx.lineTo(150, 34); ctx.lineTo(0, 8); ctx.fill();
      ctx.restore();
    }
    ctx.fillStyle = theme.shadow; rr(-CAR_LEN + 3, -CAR_W / 2 + 4, CAR_LEN, CAR_W, 7); ctx.fill();
    ctx.fillStyle = c.colour; rr(-CAR_LEN, -CAR_W / 2, CAR_LEN, CAR_W, 7); ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,.35)'; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = 'rgba(15,23,42,.55)'; rr(-22, -CAR_W / 2 + 4, 10, CAR_W - 8, 3); ctx.fill();
    ctx.fillStyle = 'rgba(15,23,42,.4)'; rr(-CAR_LEN + 6, -CAR_W / 2 + 5, 7, CAR_W - 10, 3); ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,.12)'; rr(-CAR_LEN + 15, -CAR_W / 2 + 5, CAR_LEN - 38, CAR_W - 10, 4); ctx.fill();
    ctx.fillStyle = '#fffbe6'; ctx.fillRect(-3, -CAR_W / 2 + 3, 3, 6); ctx.fillRect(-3, CAR_W / 2 - 9, 3, 6);
    ctx.fillStyle = c.braking ? '#ff2a2a' : '#7f1d1d';
    ctx.fillRect(-CAR_LEN, -CAR_W / 2 + 3, 3, 7); ctx.fillRect(-CAR_LEN, CAR_W / 2 - 10, 3, 7);
    ctx.restore();
    if (c.braking) glow(carX(lane, c.s - CAR_LEN), y, 24, '#ff2828', theme.night ? 0.5 : 0.35);
  }

  function drawPed(p, t) {
    const moving = p.state !== 'waiting';
    const bob = moving ? Math.sin(p.walkT * 10) * 1.2 : 0;
    ctx.fillStyle = theme.shadow; ctx.beginPath(); ctx.arc(p.x + 2, p.y + 3, 9, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = p.colour; ctx.beginPath(); ctx.ellipse(p.x, p.y + bob, 10, 7.5, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#f1c9a5'; ctx.beginPath(); ctx.arc(p.x, p.y + bob, 5, 0, Math.PI * 2); ctx.fill();
  }

  // Pictogram man. walking=false → standing red man.
  function man(cx, cy, s, colour, walking) {
    ctx.save();
    ctx.translate(cx, cy); ctx.scale(s, s);
    ctx.fillStyle = colour; ctx.strokeStyle = colour; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.arc(walking ? 1 : 0, -15, 4, 0, Math.PI * 2); ctx.fill();
    ctx.lineWidth = 5;
    ctx.beginPath();
    if (walking) {
      ctx.moveTo(0, -9); ctx.lineTo(-1, 4);          // torso
      ctx.moveTo(-1, 3); ctx.lineTo(-7, 17);         // back leg
      ctx.moveTo(-1, 3); ctx.lineTo(5, 10); ctx.lineTo(6, 17); // front leg
      ctx.moveTo(0, -7); ctx.lineTo(-7, 1);          // back arm
      ctx.moveTo(0, -7); ctx.lineTo(7, -1);          // front arm
    } else {
      ctx.moveTo(0, -9); ctx.lineTo(0, 4);
      ctx.moveTo(-3, 3); ctx.lineTo(-3, 17);
      ctx.moveTo(3, 3); ctx.lineTo(3, 17);
      ctx.moveTo(-5, -7); ctx.lineTo(-6, 4);
      ctx.moveTo(5, -7); ctx.lineTo(6, 4);
    }
    ctx.stroke();
    ctx.restore();
  }

  function drawPole(x, y0, y1) {
    ctx.fillStyle = theme.night ? '#3b4452' : '#5b6472';
    ctx.fillRect(x - 4, y0, 8, y1 - y0);
    ctx.fillStyle = theme.shadow; ctx.beginPath(); ctx.ellipse(x + 3, y1, 10, 4, 0, 0, Math.PI * 2); ctx.fill();
  }

  function drawSignals(t) {
    const L = crossing.vehicleLamps;
    const P = crossing.pedestrianLamps;
    // vehicle head with white-bordered backboard (elevation view, on the near-side pole)
    const hx = 330, hy = 34;
    drawPole(hx + 38, hy + 210, ROAD_TOP - 8);
    ctx.fillStyle = '#f8fafc'; rr(hx - 8, hy - 8, 92, 224, 12); ctx.fill();
    ctx.fillStyle = '#0b0f14'; rr(hx - 2, hy - 2, 80, 212, 9); ctx.fill();
    const lamps = [['red', '#ff3b3b', 36], ['amber', '#ffb020', 104], ['green', '#2ee86b', 172]];
    for (const [name, col, ly] of lamps) {
      const cx = hx + 38, cy = hy + ly;
      ctx.fillStyle = '#05070a'; ctx.beginPath(); ctx.arc(cx, cy, 28, Math.PI, 0); ctx.fill(); // visor shadow
      if (L[name]) glow(cx, cy, 62, col, 0.55);
      ctx.fillStyle = L[name] ? col : theme.lampOff;
      ctx.beginPath(); ctx.arc(cx, cy, 25, 0, Math.PI * 2); ctx.fill();
      if (!L[name]) { ctx.fillStyle = hexA(col, 0.12); ctx.beginPath(); ctx.arc(cx, cy, 25, 0, Math.PI * 2); ctx.fill(); }
      else { ctx.fillStyle = 'rgba(255,255,255,.5)'; ctx.beginPath(); ctx.arc(cx - 8, cy - 8, 7, 0, Math.PI * 2); ctx.fill(); }
    }

    // pedestrian signal box (far-side style, on the pole by the crossing)
    const px = 586, py = 60;
    drawPole(px + 44, py + 180, ROAD_TOP - 8);
    ctx.fillStyle = '#0b0f14'; rr(px, py, 88, 182, 10); ctx.fill();
    ctx.strokeStyle = '#2a323d'; ctx.lineWidth = 2; ctx.stroke();
    for (const [lit, col, cy, walking] of [[P.redMan, '#ff3b3b', py + 47, false], [P.greenMan, '#2ee86b', py + 135, true]]) {
      ctx.fillStyle = '#05070a'; rr(px + 10, cy - 38, 68, 76, 6); ctx.fill();
      if (lit) glow(px + 44, cy, 70, col, 0.45);
      man(px + 44, cy + 2, 1.65, lit ? col : hexA(col, 0.13), walking);
    }

    // yellow push-button box with WAIT lamp
    const b = BUTTON_BOX;
    drawPole(b.x + b.w / 2, b.y + b.h, ROAD_TOP - 8);
    ctx.fillStyle = theme.shadow; rr(b.x + 3, b.y + 4, b.w, b.h, 8); ctx.fill();
    ctx.fillStyle = '#f6c400'; rr(b.x, b.y, b.w, b.h, 8); ctx.fill();
    ctx.strokeStyle = '#a07f00'; ctx.lineWidth = 2; ctx.stroke();
    const wait = crossing.waitIndicator;
    ctx.fillStyle = '#111'; rr(b.x + 8, b.y + 10, b.w - 16, 24, 4); ctx.fill();
    if (wait) glow(b.x + b.w / 2, b.y + 22, 44, '#ff9f1a', 0.55);
    ctx.fillStyle = wait ? '#ffb340' : '#3a3a3a';
    ctx.font = '800 14px ui-monospace, Menlo, Consolas, monospace';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('WAIT', b.x + b.w / 2, b.y + 23);
    // button
    const bp = pulse > 0 ? 1 - pulse * 0.3 : 1;
    ctx.fillStyle = '#2b2b2b'; ctx.beginPath(); ctx.arc(b.x + b.w / 2, b.y + 64, 15, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#d4d4d8'; ctx.beginPath(); ctx.arc(b.x + b.w / 2, b.y + 64, 11 * bp, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#111';
    ctx.font = '700 9px ui-sans-serif, system-ui, sans-serif';
    ctx.fillText('PUSH', b.x + b.w / 2, b.y + 90);
    ctx.fillText('BUTTON', b.x + b.w / 2, b.y + 101);

    // labels
    ctx.fillStyle = theme.night ? '#cbd5e1' : '#334155';
    ctx.font = '600 13px ui-sans-serif, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Traffic signal', hx + 38, 18);
    ctx.fillText('Pedestrians', px + 44, py - 14);
  }

  function draw(t) {
    const { dpr, k, ox, oy } = view;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = theme.grass; ctx.fillRect(0, 0, view.w, view.h);
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * ox, dpr * oy);
    drawRoad();
    if (crossing.pedestrianSignal !== 'dont_walk' && (crossing.pedestrianSignal === 'walk' || crossing.flashOn)) {
      ctx.fillStyle = 'rgba(34,197,94,.16)';
      ctx.fillRect(XING_L, ROAD_TOP, XING_R - XING_L, ROAD_BOT - ROAD_TOP);
    }
    for (const lane of ['E', 'W']) for (const c of cars[lane]) drawCar(lane, c, t);
    for (const p of peds) drawPed(p, t);
    drawSignals(t);
  }

  // ------------------------------------------------------------------- loop
  renderSequenceTimes();
  if (params.get('fast') === '1') setFast(true);
  let last = performance.now();
  let lastPanel = 0;
  function frame(now) {
    const dt = Math.min(0.1, Math.max(0, (now - last) / 1000));
    last = now;
    crossing.tick(dt);
    stepCars(dt);
    stepPeds(dt);
    pulse = Math.max(0, pulse - dt * 3);
    draw(now / 1000);
    if (now - lastPanel > 100) { lastPanel = now; updatePanel(); }
    requestAnimationFrame(frame);
  }
  updatePanel();
  requestAnimationFrame(frame);

  // console / test hook
  window.greenwaveClassic = {
    get crossing() { return crossing; },
    press,
    advance(seconds, step = 0.05) { for (let s = 0; s < seconds; s += step) { crossing.tick(step); stepCars(step); stepPeds(step); } },
  };
}

function hexA(hex, a) {
  if (!hex.startsWith('#')) return hex;
  const n = parseInt(hex.slice(1, 7), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}
