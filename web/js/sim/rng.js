// Seeded pseudo-random number generation (mulberry32).
// Deterministic: the same seed always yields the same sequence.

/** Create a seeded RNG returning floats in [0, 1). */
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Small RNG wrapper with handy distributions. */
export class Rng {
  constructor(seed = 42) {
    this.seed = seed >>> 0;
    this._next = mulberry32(this.seed);
  }

  /** Uniform float in [0, 1). */
  random() {
    return this._next();
  }

  /** Uniform float in [min, max). */
  uniform(min, max) {
    return min + (max - min) * this._next();
  }

  /** Integer in [min, max] inclusive. */
  int(min, max) {
    return min + Math.floor(this._next() * (max - min + 1));
  }

  /** Pick a random element of an array. */
  pick(arr) {
    return arr[Math.floor(this._next() * arr.length)];
  }

  /** Exponential variate with the given rate (events per unit time). */
  exponential(rate) {
    if (!(rate > 0)) return Infinity;
    return -Math.log(1 - this._next()) / rate;
  }
}
