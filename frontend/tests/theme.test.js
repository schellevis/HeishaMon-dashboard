import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { THEME_KEY, initTheme, resolvedTheme, setTheme, themeChoice } from '../src/lib/theme.js';

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return { getItem: (k) => data[k] ?? null, setItem: (k, v) => { data[k] = String(v); }, removeItem: (k) => { delete data[k]; }, data };
}
function media(light) {
  const listeners = new Set();
  return {
    matches: light,
    addEventListener: (_, fn) => listeners.add(fn),
    removeEventListener: (_, fn) => listeners.delete(fn),
    fire(next) { this.matches = next; for (const fn of listeners) fn({ matches: next }); },
  };
}

describe('theme', () => {
  it('follows the system until a choice is stored', () => {
    const root = document.createElement('html');
    const m = media(true);
    const stop = initTheme({ storage: memoryStorage(), media: m, root });
    expect(get(resolvedTheme)).toBe('day');
    expect(root.dataset.theme).toBe('day');
    m.fire(false);
    expect(get(resolvedTheme)).toBe('night');
    expect(root.dataset.theme).toBe('night');
    stop();
  });
  it('restores and persists an explicit choice', () => {
    const root = document.createElement('html');
    const storage = memoryStorage({ [THEME_KEY]: 'night' });
    const stop = initTheme({ storage, media: media(true), root });
    expect(get(themeChoice)).toBe('night');
    expect(root.dataset.theme).toBe('night');
    setTheme('day');
    expect(storage.data[THEME_KEY]).toBe('day');
    expect(root.dataset.theme).toBe('day');
    setTheme(null);
    expect(storage.data[THEME_KEY]).toBeUndefined();
    stop();
  });
  it('ignores a garbage stored value', () => {
    const root = document.createElement('html');
    const stop = initTheme({ storage: memoryStorage({ [THEME_KEY]: 'pink' }), media: media(false), root });
    expect(get(themeChoice)).toBe(null);
    expect(root.dataset.theme).toBe('night');
    stop();
  });
});
