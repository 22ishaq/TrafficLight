// Canvas renderer for the junction. Pure presentation: reads simulation state, never mutates it.
import * as E from './sim/engine.js';

const STOP_LINE = E.STOP_LINE ?? E.LANE_LENGTH ?? 160;
const BOX = E.BOX ?? 24;
const HALF_BOX = BOX / 2;
const CENTRE = STOP_LINE + HALF_BOX;   // distance from spawn point to junction centre

const ROAD_HALF = 4.2;                // half-width of each road (one lane each way)
const LANE_OFF = 2.0;                 // lane centre offset from road centre line
const CAR_WIDTH = 1.85;
const VIEW = 56;                      // metres visible from centre to edge

// Crossing band on each arm, measured as distance from centre.
const XWALK_NEAR = 8.3;
const XWALK_FAR = 11.4;

// Heading of travel per approach (approach = side the vehicle comes FROM). Drive on the LEFT.
const HEADING = { N: Math.PI / 2, S: -Math.PI / 2, E: Math.PI, W: 0 };

const CAR_COLOURS = ['#e11d48', '#2563eb', '#f8fafc', '#0f172a', '#64748b', '#0891b2', '#16a34a', '#f97316', '#7c3aed', '#ca8a04', '#94a3b8', '#be123c'];

/** World pose of a point `pos` metres along an approach's path. */
export function pose(approach, pos) {
  switch (approach) {
    case 'N': return { x: LANE_OFF, y: -CENTRE + pos, a: HEADING.N };
    case 'S': return { x: -LANE_OFF, y: CENTRE - pos, a: HEADING.S };
    case 'E': return { x: CENTRE - pos, y: LANE_OFF, a: HEADING.E };
    default:  return { x: -CENTRE + pos, y: -LANE_OFF, a: HEADING.W };
  }
}

function cssVar(style, name, fallback) {
  const v = style.getPropertyValue(name).trim();
  return v || fallback;
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

// Small deterministic hash so decorative scenery is stable across redraws.
function hash(n) {
  let x = (n * 2654435761) >>> 0;
  x ^= x >>> 15; x = Math.imul(x, 2246822519) >>> 0; x ^= x >>> 13;
  return (x >>> 0) / 4294967296;
}

export class JunctionRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.staticLayer = document.createElement('canvas');
    this.dpr = 1;
    this.w = 0; this.h = 0; this.s = 1;
    this.theme = null;
    this.resize();
  }

  readTheme() {
    const st = getComputedStyle(document.documentElement);
    this.theme = {
      grass: cssVar(st, '--scene-grass', '#b9d7a8'),
      grass2: cssVar(st, '--scene-grass-2', '#a9cc97'),
      pavement: cssVar(st, '--scene-pavement', '#d9dde3'),
      kerb: cssVar(st, '--scene-kerb', '#9aa3ae'),
      road: cssVar(st, '--scene-road', '#4b5360'),
      roadEdge: cssVar(st, '--scene-road-edge', '#434a56'),
      marking: cssVar(st, '--scene-marking', '#f8fafc'),
      yellow: cssVar(st, '--scene-yellow', '#facc15'),
      shadow: cssVar(st, '--scene-shadow', 'rgba(0,0,0,.25)'),
      lampOff: cssVar(st, '--lamp-off', '#2b3340'),
      night: parseFloat(cssVar(st, '--scene-night', '0')) > 0.5,
    };
    this.buildStatic();
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const rect = this.canvas.getBoundingClientRect();
    const w = Math.max(200, Math.round(rect.width));
    const h = Math.max(200, Math.round(rect.height));
    if (w === this.w && h === this.h && dpr === this.dpr && this.theme) return;
    this.w = w; this.h = h; this.dpr = dpr;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.s = Math.min(w, h) / (2 * VIEW);
    if (!this.theme) this.readTheme(); else this.buildStatic();
  }

  // ---------- static scenery (cached) ----------
  buildStatic() {
    const { w, h, dpr, s } = this;
    const T = this.theme;
    const c = this.staticLayer;
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
    const ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // grass with soft mottling
    ctx.fillStyle = T.grass;
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 140; i++) {
      ctx.fillStyle = T.grass2;
      ctx.globalAlpha = 0.35 + hash(i + 7) * 0.4;
      ctx.beginPath();
      ctx.arc(hash(i) * w, hash(i + 999) * h, (6 + hash(i + 3) * 26) * s / 4, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.scale(s, s);
    const ext = Math.max(w, h) / s; // metres to cover

    // pavements (wider band around roads) with rounded corners
    const PAVE = ROAD_HALF + 2.6;
    ctx.fillStyle = T.pavement;
    ctx.fillRect(-PAVE, -ext, PAVE * 2, ext * 2);
    ctx.fillRect(-ext, -PAVE, ext * 2, PAVE * 2);

    // roads
    ctx.fillStyle = T.road;
    ctx.fillRect(-ROAD_HALF, -ext, ROAD_HALF * 2, ext * 2);
    ctx.fillRect(-ext, -ROAD_HALF, ext * 2, ROAD_HALF * 2);
    // kerb corners (rounded inside corners of the junction)
    const R = 3.2;
    for (const [sx, sy] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
      ctx.fillStyle = T.road;
      ctx.fillRect(sx > 0 ? ROAD_HALF : -ROAD_HALF - R, sy > 0 ? ROAD_HALF : -ROAD_HALF - R, R, R);
      ctx.fillStyle = T.pavement;
      ctx.beginPath();
      ctx.arc(sx * (ROAD_HALF + R), sy * (ROAD_HALF + R), R, 0, Math.PI * 2);
      ctx.fill();
    }
    // kerb edge lines
    ctx.strokeStyle = T.kerb;
    ctx.lineWidth = 0.35;
    for (const sgn of [-1, 1]) {
      for (const [a, b] of [[-ext, -ROAD_HALF - R], [ROAD_HALF + R, ext]]) {
        ctx.beginPath(); ctx.moveTo(sgn * ROAD_HALF, a); ctx.lineTo(sgn * ROAD_HALF, b); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(a, sgn * ROAD_HALF); ctx.lineTo(b, sgn * ROAD_HALF); ctx.stroke();
      }
    }
    for (const [sx, sy] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
      const cx = sx * (ROAD_HALF + R), cy = sy * (ROAD_HALF + R);
      const start = Math.atan2(-sy, -sx) - Math.PI / 4;
      ctx.beginPath();
      ctx.arc(cx, cy, R, start, start + Math.PI / 2);
      ctx.stroke();
    }

    // road texture: subtle edge darkening
    ctx.fillStyle = T.roadEdge;
    for (const sgn of [-1, 1]) {
      ctx.fillRect(sgn > 0 ? ROAD_HALF - 0.5 : -ROAD_HALF, -ext, 0.5, ext - ROAD_HALF - R);
      ctx.fillRect(sgn > 0 ? ROAD_HALF - 0.5 : -ROAD_HALF, ROAD_HALF + R, 0.5, ext);
      ctx.fillRect(-ext, sgn > 0 ? ROAD_HALF - 0.5 : -ROAD_HALF, ext - ROAD_HALF - R, 0.5);
      ctx.fillRect(ROAD_HALF + R, sgn > 0 ? ROAD_HALF - 0.5 : -ROAD_HALF, ext, 0.5);
    }

    // markings, drawn once per arm in a rotated frame where the arm points "up" (−y)
    for (const rot of [0, Math.PI / 2, Math.PI, -Math.PI / 2]) {
      ctx.save();
      ctx.rotate(rot);
      this.drawArmMarkings(ctx, ext);
      ctx.restore();
    }

    // UK yellow box junction hatching
    ctx.save();
    ctx.beginPath();
    ctx.rect(-ROAD_HALF + 0.4, -ROAD_HALF + 0.4, (ROAD_HALF - 0.4) * 2, (ROAD_HALF - 0.4) * 2);
    ctx.strokeStyle = T.yellow;
    ctx.lineWidth = 0.22;
    ctx.globalAlpha = 0.85;
    ctx.stroke();
    ctx.clip();
    for (let d = -12; d <= 12; d += 1.6) {
      ctx.beginPath(); ctx.moveTo(d - 10, -10); ctx.lineTo(d + 10, 10); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(d + 10, -10); ctx.lineTo(d - 10, 10); ctx.stroke();
    }
    ctx.restore();

    // trees on the grass corners
    for (let i = 0; i < 26; i++) {
      const qx = hash(i * 3 + 1) > 0.5 ? 1 : -1;
      const qy = hash(i * 5 + 2) > 0.5 ? 1 : -1;
      const tx = qx * (PAVE + 6 + hash(i * 7 + 3) * (VIEW * 1.6 - PAVE - 6));
      const ty = qy * (PAVE + 6 + hash(i * 11 + 4) * (VIEW - PAVE - 6));
      const r = 2.2 + hash(i * 13 + 5) * 2.4;
      ctx.fillStyle = T.shadow;
      ctx.beginPath(); ctx.arc(tx + 0.9, ty + 1.1, r, 0, Math.PI * 2); ctx.fill();
      const g = ctx.createRadialGradient(tx - r * 0.35, ty - r * 0.35, r * 0.1, tx, ty, r);
      g.addColorStop(0, T.night ? '#2f5a3a' : '#7fbf6a');
      g.addColorStop(1, T.night ? '#173322' : '#3f7d3a');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(tx, ty, r, 0, Math.PI * 2); ctx.fill();
    }

    // street lamps (posts on the pavement); pools of light at night
    const lamps = [[PAVE - 0.8, -22], [-PAVE + 0.8, 22], [22, PAVE - 0.8], [-22, -PAVE + 0.8], [PAVE - 0.8, -48], [-PAVE + 0.8, 48], [48, PAVE - 0.8], [-48, -PAVE + 0.8], [76, -PAVE + 0.8], [-76, PAVE - 0.8]];
    if (T.night) {
      ctx.globalCompositeOperation = 'lighter';
      for (const [lx, ly] of lamps) {
        const g = ctx.createRadialGradient(lx, ly, 0, lx, ly, 11);
        g.addColorStop(0, 'rgba(255, 196, 120, .30)');
        g.addColorStop(1, 'rgba(255, 196, 120, 0)');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(lx, ly, 11, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalCompositeOperation = 'source-over';
    }
    for (const [lx, ly] of lamps) {
      ctx.fillStyle = T.night ? '#ffd9a0' : '#6b7280';
      ctx.beginPath(); ctx.arc(lx, ly, 0.45, 0, Math.PI * 2); ctx.fill();
    }

    ctx.restore();
  }

  // Markings for the arm that extends towards −y (top). Inbound lane (top arm = approach N) is on +x.
  drawArmMarkings(ctx, ext) {
    const T = this.theme;
    ctx.strokeStyle = T.marking;
    ctx.fillStyle = T.marking;

    // centre line: long warning dashes near the junction, normal dashes further out
    ctx.lineWidth = 0.15;
    ctx.setLineDash([]);
    for (let y = -HALF_BOX - 1; y > -ext; ) {
      const warn = y > -HALF_BOX - 30;
      const dash = warn ? 6 : 3;
      const gap = warn ? 1.5 : 6;
      ctx.fillRect(-0.08, y - dash, 0.16, dash);
      y -= dash + gap;
    }

    // stop line across the inbound lane only (+x side)
    ctx.fillRect(0.1, -HALF_BOX - 0.3, ROAD_HALF - 0.3, 0.3);
    // give-way style give "elbow" studs at kerb on outbound lane (subtle)
    ctx.globalAlpha = 0.5;
    for (let x = -ROAD_HALF + 0.6; x < 0; x += 1) ctx.fillRect(x, -HALF_BOX - 0.15, 0.4, 0.15);
    ctx.globalAlpha = 1;

    // crossing: zebra-style stripes
    for (let x = -ROAD_HALF + 0.35; x < ROAD_HALF - 0.4; x += 1.0) {
      ctx.fillRect(x, -XWALK_FAR, 0.55, XWALK_FAR - XWALK_NEAR);
    }

    // lane arrows (ahead) in inbound lane
    ctx.save();
    ctx.translate(LANE_OFF, -HALF_BOX - 9);
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.moveTo(-0.18, -3.4); ctx.lineTo(0.18, -3.4); ctx.lineTo(0.18, 0); ctx.lineTo(0.7, 0);
    ctx.lineTo(0, 1.6); ctx.lineTo(-0.7, 0); ctx.lineTo(-0.18, 0); ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  // ---------- per-frame ----------
  draw(sim, realTime) {
    const { ctx, dpr, w, h, s } = this;
    const T = this.theme;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(this.staticLayer, 0, 0);
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * w / 2, dpr * h / 2);

    const pedState = safeCall(() => sim.pedestrianState(), 'dont_walk');
    if (pedState !== 'dont_walk') this.drawCrossingGlow(ctx, pedState, realTime);

    const vehicles = sim.vehicles || [];
    if (T.night) this.drawHeadlights(ctx, vehicles);
    for (const v of vehicles) this.drawVehicle(ctx, v, realTime, false);
    this.drawPedestrians(ctx, sim, pedState, realTime);
    for (const a of ['N', 'E', 'S', 'W']) this.drawSignalHead(ctx, a, safeCall(() => sim.lightFor(a), 'red'), realTime);
    for (const v of vehicles) if (v.emergency) this.drawVehicle(ctx, v, realTime, true);
  }

  drawCrossingGlow(ctx, pedState, t) {
    const on = pedState === 'walk' || Math.floor(t * 2.5) % 2 === 0;
    if (!on) return;
    ctx.save();
    ctx.globalAlpha = pedState === 'walk' ? 0.22 : 0.16;
    ctx.fillStyle = '#22c55e';
    for (const rot of [0, Math.PI / 2, Math.PI, -Math.PI / 2]) {
      ctx.save(); ctx.rotate(rot);
      ctx.fillRect(-ROAD_HALF - 0.6, -XWALK_FAR - 0.3, ROAD_HALF * 2 + 1.2, XWALK_FAR - XWALK_NEAR + 0.6);
      ctx.restore();
    }
    ctx.restore();
  }

  drawHeadlights(ctx, vehicles) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const v of vehicles) {
      const p = pose(v.approach, v.pos);
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.a);
      const g = ctx.createLinearGradient(0, 0, 16, 0);
      g.addColorStop(0, 'rgba(255, 244, 200, .38)');
      g.addColorStop(1, 'rgba(255, 244, 200, 0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(0, -0.7); ctx.lineTo(16, -3.6); ctx.lineTo(16, 3.6); ctx.lineTo(0, 0.7);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
    ctx.restore();
  }

  drawVehicle(ctx, v, t, overlayOnly) {
    const p = pose(v.approach, v.pos);
    const L = v.length || 4.5;
    const W = v.width || (v.emergency ? 2.1 : CAR_WIDTH);
    const night = this.theme.night;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(p.a);

    if (overlayOnly) {
      // flashing blue light glow on top of everything
      const phase = Math.floor(t * 6) % 2;
      ctx.globalCompositeOperation = 'lighter';
      const gx = -L * 0.45, gy = phase ? -0.6 : 0.6;
      const g = ctx.createRadialGradient(gx, gy, 0, gx, gy, 7);
      g.addColorStop(0, 'rgba(70, 140, 255, .55)');
      g.addColorStop(1, 'rgba(70, 140, 255, 0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(gx, gy, 7, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      return;
    }

    // shadow
    ctx.fillStyle = this.theme.shadow;
    roundRect(ctx, -L + 0.25, -W / 2 + 0.3, L, W, 0.55);
    ctx.fill();

    // body
    let body = v.color || CAR_COLOURS[(Number(v.id) || 0) % CAR_COLOURS.length];
    if (v.emergency) body = '#e9f542';
    ctx.fillStyle = body;
    roundRect(ctx, -L, -W / 2, L, W, 0.55);
    ctx.fill();
    ctx.lineWidth = 0.08;
    ctx.strokeStyle = 'rgba(0,0,0,.35)';
    ctx.stroke();

    if (v.emergency) {
      // Battenburg-style checks along the sides
      ctx.save();
      roundRect(ctx, -L, -W / 2, L, W, 0.55);
      ctx.clip();
      ctx.fillStyle = '#1d4ed8';
      for (let x = -L, i = 0; x < 0; x += 0.7, i++) {
        ctx.fillRect(x, i % 2 ? -W / 2 : W / 2 - 0.35, 0.7, 0.35);
        ctx.fillRect(x, i % 2 ? W / 2 - 0.35 : -W / 2, 0.7, 0.35);
      }
      ctx.restore();
      // light bar
      const phase = Math.floor(t * 6) % 2;
      ctx.fillStyle = phase ? '#3b82f6' : '#0b1e4a';
      ctx.fillRect(-L * 0.55, -W / 2 + 0.25, 0.5, W / 2 - 0.25);
      ctx.fillStyle = phase ? '#0b1e4a' : '#3b82f6';
      ctx.fillRect(-L * 0.55, 0, 0.5, W / 2 - 0.25);
    } else if (v.kind === 'bus') {
      ctx.fillStyle = 'rgba(15, 23, 42, .55)';
      roundRect(ctx, -1.1, -W / 2 + 0.2, 0.6, W - 0.4, 0.2);
      ctx.fill();
      ctx.fillStyle = 'rgba(15, 23, 42, .28)';
      for (let x = -L + 0.6; x < -1.6; x += 1.4) {
        ctx.fillRect(x, -W / 2 + 0.12, 1.0, 0.3);
        ctx.fillRect(x, W / 2 - 0.42, 1.0, 0.3);
      }
      ctx.fillStyle = 'rgba(255,255,255,.18)';
      ctx.fillRect(-L + 0.5, -0.5, L - 2, 1.0);
    } else {
      // windscreen + rear window
      ctx.fillStyle = 'rgba(15, 23, 42, .55)';
      roundRect(ctx, -1.65, -W / 2 + 0.22, 0.75, W - 0.44, 0.2);
      ctx.fill();
      ctx.fillStyle = 'rgba(15, 23, 42, .4)';
      roundRect(ctx, -L + 0.45, -W / 2 + 0.28, 0.5, W - 0.56, 0.18);
      ctx.fill();
      // roof highlight
      ctx.fillStyle = 'rgba(255,255,255,.12)';
      roundRect(ctx, -L + 1.05, -W / 2 + 0.3, L - 2.8, W - 0.6, 0.3);
      ctx.fill();
    }

    // headlights
    ctx.fillStyle = night ? '#fffbe6' : 'rgba(255, 251, 230, .85)';
    ctx.fillRect(-0.18, -W / 2 + 0.15, 0.18, 0.38);
    ctx.fillRect(-0.18, W / 2 - 0.53, 0.18, 0.38);

    // brake / tail lights
    const braking = !!v.braking;
    ctx.fillStyle = braking ? '#ff2a2a' : (night ? '#9b1c1c' : '#7f1d1d');
    ctx.fillRect(-L, -W / 2 + 0.12, 0.2, 0.45);
    ctx.fillRect(-L, W / 2 - 0.57, 0.2, 0.45);
    if (braking) {
      ctx.globalCompositeOperation = 'lighter';
      const g = ctx.createRadialGradient(-L, 0, 0, -L, 0, 2.2);
      g.addColorStop(0, night ? 'rgba(255, 40, 40, .55)' : 'rgba(255, 40, 40, .35)');
      g.addColorStop(1, 'rgba(255, 40, 40, 0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(-L, 0, 2.2, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  drawPedestrians(ctx, sim, pedState, t) {
    let peds = Array.isArray(sim.pedestrians) ? sim.pedestrians : null;
    if (!peds && pedState !== 'dont_walk') peds = fallbackPedestrians(sim);
    if (!peds || !peds.length) return;
    const colours = ['#f43f5e', '#0ea5e9', '#a855f7', '#f59e0b', '#10b981', '#e2e8f0'];
    for (const p of peds) {
      const id = Number(p.id) || 0;
      const bob = Math.sin(t * 9 + id) * 0.08;
      ctx.fillStyle = this.theme.shadow;
      ctx.beginPath(); ctx.arc(p.x + 0.15, p.y + 0.2, 0.42, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = p.color || colours[id % colours.length];
      ctx.beginPath(); ctx.ellipse(p.x, p.y + bob, 0.45, 0.32, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#f1c9a5';
      ctx.beginPath(); ctx.arc(p.x, p.y + bob, 0.22, 0, Math.PI * 2); ctx.fill();
    }
  }

  drawSignalHead(ctx, approach, state, t) {
    // place the head on the near-side (left) kerb, just before the stop line
    const k = ROAD_HALF + 1.5;
    const d = HALF_BOX + 1.2;
    let x, y, a;
    switch (approach) {
      case 'N': x = k; y = -d; a = HEADING.N; break;
      case 'S': x = -k; y = d; a = HEADING.S; break;
      case 'E': x = d; y = k; a = HEADING.E; break;
      default:  x = -d; y = -k; a = HEADING.W;
    }
    const px = 1 / this.s;                    // one CSS pixel in metres
    const r = Math.min(7, Math.max(3.2, this.s * 0.78)) * px;  // lamp radius in CSS px, kept readable
    const gap = r * 2.5;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(a);
    // housing: red upstream (−x local), green towards the junction (+x local)
    ctx.fillStyle = 'rgba(0,0,0,.35)';
    roundRect(ctx, -gap - r * 1.5 + px * 1.5, -r * 1.5 + px * 1.5, gap * 2 + r * 3, r * 3, r * 0.8);
    ctx.fill();
    ctx.fillStyle = '#0f1419';
    roundRect(ctx, -gap - r * 1.5, -r * 1.5, gap * 2 + r * 3, r * 3, r * 0.8);
    ctx.fill();
    ctx.strokeStyle = '#2a323d';
    ctx.lineWidth = px;
    ctx.stroke();

    const lit = {
      red: state === 'red' || state === 'red_amber',
      amber: state === 'amber' || state === 'red_amber',
      green: state === 'green',
    };
    const lamps = [['red', -gap, '#ff3b3b'], ['amber', 0, '#ffb020'], ['green', gap, '#2ee86b']];
    for (const [name, lx, colour] of lamps) {
      if (lit[name]) {
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        const g = ctx.createRadialGradient(lx, 0, 0, lx, 0, r * 3.4);
        g.addColorStop(0, hexA(colour, 0.65));
        g.addColorStop(1, hexA(colour, 0));
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(lx, 0, r * 3.4, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
        ctx.fillStyle = colour;
      } else {
        ctx.fillStyle = this.theme.lampOff;
      }
      ctx.beginPath(); ctx.arc(lx, 0, r, 0, Math.PI * 2); ctx.fill();
      if (lit[name]) {
        ctx.fillStyle = 'rgba(255,255,255,.55)';
        ctx.beginPath(); ctx.arc(lx - r * 0.3, -r * 0.3, r * 0.32, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.restore();
  }
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function safeCall(fn, fallback) {
  try { const v = fn(); return v ?? fallback; } catch { return fallback; }
}

// Decorative walkers used only if the engine doesn't expose `pedestrians`.
function fallbackPedestrians(sim) {
  const t = sim.signal?.phaseTime ?? 0;
  const out = [];
  const mid = (XWALK_NEAR + XWALK_FAR) / 2;
  let id = 0;
  for (let arm = 0; arm < 4; arm++) {
    for (let k = 0; k < 3; k++) {
      const dir = (k + arm) % 2 ? 1 : -1;
      const prog = Math.min(1, (t * 0.75 + k * 1.9) / (ROAD_HALF * 2 + 3));
      const along = dir * (-(ROAD_HALF + 1.5) + prog * (ROAD_HALF * 2 + 3));
      const lane = mid + (k - 1) * 1.2;
      let x, y;
      if (arm === 0) { x = along; y = -lane; }
      else if (arm === 1) { x = lane; y = along; }
      else if (arm === 2) { x = -along; y = lane; }
      else { x = -lane; y = -along; }
      out.push({ id: id++, x, y, progress: prog });
    }
  }
  return out;
}
