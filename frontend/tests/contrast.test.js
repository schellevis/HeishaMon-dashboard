import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Read from disk: Vitest stubs CSS imports (even ?raw) to an empty string.
const css = readFileSync(resolve(process.cwd(), 'src/app.css'), 'utf8');

function block(selector) {
  const start = css.indexOf(selector);
  return css.slice(start, css.indexOf('}', start));
}
function vars(text) {
  return Object.fromEntries([...text.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}
function luminance(hex) {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe('text contrast', () => {
  for (const [name, selector] of [['night', ":root[data-theme='night']"], ['day', ":root[data-theme='day']"]]) {
    it(`meets 4.5:1 for functional text in ${name}`, () => {
      const v = vars(block(selector));
      for (const fg of ['ink', 'ink-2', 'ink-3', 'ok-ink', 'pending-ink', 'fail-ink', 'warm-ink']) {
        for (const bg of ['panel', 'panel-2', 'ground']) {
          expect(ratio(v[fg], v[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    });
  }
});
