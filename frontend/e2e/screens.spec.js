import { test, expect } from '@playwright/test';
import { up, down } from './stack.js';
import { SCREENS, noOverflow, openScreen, watchErrors } from './helpers.js';

const PRESETS = ['heat_only', 'heat_dhw', 'auto_cool_mode7', 'two_zones_heat_curve_cool_direct', 'fw-3.2.3', 'pcb_active'];

for (const preset of PRESETS) {
  test.describe(`screens @ ${preset}`, () => {
    test.beforeAll(async () => { await up(preset); });
    test.afterAll(async () => { await down(); });

    for (const [width, height] of [[1280, 800], [390, 844]]) {
      for (const name of SCREENS) {
        test(`${name} loads without horizontal overflow at ${width}px`, async ({ page }) => {
          const errors = watchErrors(page);
          await page.setViewportSize({ width, height });
          await openScreen(page, name);
          await page.waitForTimeout(500); // let async data render before measuring
          await noOverflow(page);
          expect(errors).toEqual([]);
        });
      }
    }
  });
}

test.describe('language switch', () => {
  test.beforeAll(async () => { await up('heat_dhw'); });
  test.afterAll(async () => { await down(); });

  test('EN/NL switch changes navigation labels and persists across reload', async ({ page }) => {
    await openScreen(page, 'overview');
    await page.getByTestId('lang-nl').click();
    await expect(page.getByTestId('nav-settings')).toHaveText('Instellingen');
    await expect(page.getByTestId('lang-nl')).toHaveAttribute('aria-pressed', 'true');
    await page.reload();
    await expect(page.getByTestId('nav-settings')).toHaveText('Instellingen');
    await page.getByTestId('lang-en').click();
    await expect(page.getByTestId('nav-settings')).toHaveText('Settings');
  });
});
