/** Temperature colours (spec 2026-10-14 §2): one cold→warm ramp for everything that is a temperature. */

export const RAMP = [
  [15, [79, 163, 224]],
  [28, [143, 184, 201]],
  [38, [240, 160, 75]],
  [55, [229, 83, 61]],
];

/** Non-temperature marks shared by charts: neutral grey and the "after" / ok green. */
export const MARK_RGB = { neutral: [147, 163, 176], ok: [108, 197, 154] };

/** CSS variable per activity; the same colour marks an activity everywhere. */
export const ACTIVITY_VAR = {
  heating: '--warm',
  dhw: '--hot',
  cooling: '--cold',
  defrost: '--cool',
  idle: '--line-2',
};

export function mixRgb(a, b, f) {
  return `rgb(${a.map((x, i) => Math.round(x + (b[i] - x) * f)).join(',')})`;
}

export function tempColor(t) {
  if (t === null || t === undefined || !Number.isFinite(t)) return 'var(--pipe-idle)';
  if (t <= RAMP[0][0]) return mixRgb(RAMP[0][1], RAMP[0][1], 0);
  for (let i = 1; i < RAMP.length; i++) {
    const [t1, c1] = RAMP[i];
    if (t <= t1) {
      const [t0, c0] = RAMP[i - 1];
      return mixRgb(c0, c1, (t - t0) / (t1 - t0));
    }
  }
  const last = RAMP[RAMP.length - 1][1];
  return mixRgb(last, last, 0);
}
