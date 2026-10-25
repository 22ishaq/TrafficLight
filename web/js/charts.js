// Tiny dependency-free canvas charts: a dual-axis line chart and a signal timeline strip.

function setupCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(50, Math.round(rect.width));
  const h = Math.max(10, Math.round(rect.height));
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function token(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/**
 * Dual-axis line chart. `series` = [{ key, color, label, unit, axis: 'left'|'right', fill }].
 */
export class LineChart {
  constructor(canvas, series) {
    this.canvas = canvas;
    this.series = series;
  }

  draw(data) {
    const { ctx, w, h } = setupCanvas(this.canvas);
    const grid = token('--chart-grid', '#e5e9ef');
    const muted = token('--muted', '#5b6676');
    ctx.clearRect(0, 0, w, h);
    const pad = { l: 30, r: 34, t: 8, b: 18 };
    const pw = w - pad.l - pad.r;
    const ph = h - pad.t - pad.b;

    const maxes = {};
    for (const s of this.series) {
      let m = 0;
      for (const d of data) m = Math.max(m, Number(d[s.key]) || 0);
      maxes[s.axis] = Math.max(maxes[s.axis] || 0, m);
    }
    const left = niceMax(maxes.left || 1);
    const right = niceMax(maxes.right || 1);

    ctx.font = '10.5px ui-monospace, Menlo, Consolas, monospace';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + ph - (ph * i) / 4;
      ctx.strokeStyle = grid;
      ctx.beginPath(); ctx.moveTo(pad.l, Math.round(y) + 0.5); ctx.lineTo(w - pad.r, Math.round(y) + 0.5); ctx.stroke();
      ctx.fillStyle = muted;
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillText(fmt(left * i / 4), pad.l - 5, y);
      ctx.textAlign = 'left';
      ctx.fillText(fmt(right * i / 4) + 's', w - pad.r + 5, y);
    }

    if (data.length < 2) {
      ctx.fillStyle = muted;
      ctx.textAlign = 'center';
      ctx.fillText('collecting data…', pad.l + pw / 2, pad.t + ph / 2);
      return;
    }

    const t0 = data[0].t, t1 = data[data.length - 1].t;
    const span = Math.max(1, t1 - t0);
    const xOf = (t) => pad.l + ((t - t0) / span) * pw;

    // time labels
    ctx.fillStyle = muted;
    ctx.textBaseline = 'alphabetic';
    ctx.textAlign = 'left';
    ctx.fillText(clock(t0), pad.l, h - 4);
    ctx.textAlign = 'right';
    ctx.fillText(clock(t1), w - pad.r, h - 4);

    for (const s of this.series) {
      const max = s.axis === 'right' ? right : left;
      const color = token(s.colorVar, s.color);
      const yOf = (v) => pad.t + ph - (Math.min(v, max) / max) * ph;
      ctx.beginPath();
      data.forEach((d, i) => {
        const x = xOf(d.t), y = yOf(Number(d[s.key]) || 0);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.lineJoin = 'round';
      ctx.stroke();
      if (s.fill) {
        ctx.lineTo(xOf(t1), pad.t + ph);
        ctx.lineTo(xOf(t0), pad.t + ph);
        ctx.closePath();
        const g = ctx.createLinearGradient(0, pad.t, 0, pad.t + ph);
        g.addColorStop(0, withAlpha(color, 0.28));
        g.addColorStop(1, withAlpha(color, 0));
        ctx.fillStyle = g;
        ctx.fill();
      }
      // end dot
      const last = data[data.length - 1];
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(xOf(last.t), yOf(Number(last[s.key]) || 0), 3, 0, Math.PI * 2); ctx.fill();
    }
  }
}

/** Horizontal strip showing the recent colour history of one signal group. */
export class SignalTimeline {
  constructor(canvas, windowSeconds = 120) {
    this.canvas = canvas;
    this.window = windowSeconds;
    this.samples = []; // { t, state }
  }

  reset() { this.samples = []; }

  push(t, state) {
    const last = this.samples[this.samples.length - 1];
    if (last && last.state === state && t - last.t < 1) return;
    this.samples.push({ t, state });
    const cutoff = t - this.window - 2;
    while (this.samples.length > 2 && this.samples[1].t < cutoff) this.samples.shift();
  }

  draw(now) {
    const { ctx, w, h } = setupCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    const colours = {
      red: token('--lamp-red', '#ef4444'),
      amber: token('--lamp-amber', '#f59e0b'),
      green: token('--lamp-green', '#22c55e'),
    };
    const start = now - this.window;
    const xOf = (t) => ((t - start) / this.window) * w;
    for (let i = 0; i < this.samples.length; i++) {
      const s = this.samples[i];
      const tEnd = i + 1 < this.samples.length ? this.samples[i + 1].t : now;
      if (tEnd < start) continue;
      const x0 = Math.max(0, xOf(s.t)), x1 = Math.min(w, xOf(tEnd));
      if (x1 <= x0) continue;
      if (s.state === 'red_amber') {
        ctx.fillStyle = colours.red; ctx.fillRect(x0, 0, x1 - x0, h / 2);
        ctx.fillStyle = colours.amber; ctx.fillRect(x0, h / 2, x1 - x0, h / 2);
      } else {
        ctx.fillStyle = colours[s.state] || colours.red;
        ctx.fillRect(x0, 0, x1 - x0, h);
      }
    }
  }
}

function fmt(v) {
  if (v >= 100) return Math.round(v).toString();
  if (v >= 10) return v.toFixed(0);
  return v % 1 === 0 ? v.toFixed(0) : v.toFixed(1);
}

export function clock(t) {
  t = Math.max(0, Math.floor(t));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  const mm = String(m).padStart(2, '0'), ss = String(s).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function withAlpha(color, a) {
  if (color.startsWith('#')) {
    let hex = color.slice(1);
    if (hex.length === 3) hex = hex.split('').map((c) => c + c).join('');
    const n = parseInt(hex, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }
  return color;
}
