import { describe, expect, it } from 'vitest';

const files = import.meta.glob('../src/**/*.{svelte,js}', { query: '?raw', import: 'default', eager: true });
const HEX_ALLOWED = ['/lib/ui/thermal.js', '/lib/uplot.js'];
const LEGACY = /var\(--(bg|bg-secondary|bg-hover|border|text|text-secondary|primary|primary-dark|danger|warn-bg|warn-border|card-radius)\)/;

describe('design tokens', () => {
  it('uses no legacy variable names', () => {
    for (const [path, src] of Object.entries(files)) expect(LEGACY.test(src), path).toBe(false);
  });
  it('keeps hex colours out of components', () => {
    for (const [path, src] of Object.entries(files)) {
      if (HEX_ALLOWED.some((p) => path.endsWith(p)) || path.includes('/i18n/')) continue;
      const css = src.match(/<style[\s\S]*?<\/style>/g)?.join('\n') ?? '';
      const code = src.replace(/<style[\s\S]*?<\/style>/g, '');
      const hex = /#[0-9a-fA-F]{3,8}\b/;
      expect(hex.test(css), `${path} <style>`).toBe(false);
      expect(/['"`]#[0-9a-fA-F]{3,8}['"`]/.test(code), `${path} script`).toBe(false);
    }
  });
  it('colours text with the -ink variants of state and accent colours', () => {
    const accentText = /(?<![-\w])color:\s*var\(--(ok|pending|fail|warm|hot|cold|cool)\)/;
    for (const [path, src] of Object.entries(files)) {
      const css = src.match(/<style[\s\S]*?<\/style>/g)?.join('\n') ?? '';
      expect(accentText.test(css), path).toBe(false);
    }
  });
});
