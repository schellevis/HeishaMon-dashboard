import { test, expect } from '@playwright/test';
import { up, down } from './stack.js';
import { SCREENS, noOverflow, openScreen, watchErrors } from './helpers.js';

/** Product of the opacities of an element and all its ancestors. */
async function effectiveOpacity(locator) {
  return locator.evaluate((el) => {
    let o = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) o *= Number(getComputedStyle(n).opacity || 1);
    return o;
  });
}

test.describe('visual design @ heat_dhw', () => {
  test.beforeAll(async () => { await up('heat_dhw'); });
  test.afterAll(async () => { await down(); });

  test('theme toggle switches and persists', async ({ page }) => {
    await openScreen(page, 'overview');
    const before = await page.evaluate(() => document.documentElement.dataset.theme);
    await page.getByTestId('theme-toggle').click();
    const after = await page.evaluate(() => document.documentElement.dataset.theme);
    expect(after).not.toBe(before);
    await page.reload();
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(after);
  });

  test('schematic shows readings, keeps dimmed readings readable, and the timeline renders', async ({ page }) => {
    await openScreen(page, 'overview');
    await expect(page.getByTestId('plant')).toBeVisible();
    await expect(page.getByTestId('plant-flow')).not.toHaveText('—');
    await expect(page.getByTestId('timeline')).toBeVisible();
    // whichever branch is dimmed, its readings keep full opacity (spec R1 readable text)
    expect(await effectiveOpacity(page.getByTestId('plant-flow'))).toBe(1);
    expect(await effectiveOpacity(page.getByTestId('plant-dhw'))).toBe(1);
  });

  for (const theme of ['day', 'night']) {
    for (const [width, height] of [[1280, 800], [390, 844]]) {
      test(`all screens render in ${theme} at ${width}px`, async ({ page }) => {
        const errors = watchErrors(page);
        await page.addInitScript((t) => localStorage.setItem('heishamon.theme', t), theme);
        await page.setViewportSize({ width, height });
        for (const name of SCREENS) {
          await openScreen(page, name);
          await page.waitForTimeout(300);
          await noOverflow(page);
          await page.screenshot({ path: `/tmp/visual-${theme}-${width}-${name}.png`, fullPage: true });
        }
        expect(errors).toEqual([]);
      });
    }
  }
});

// Every canonical simulator preset (tools/presets.py PRESETS, aliases excluded) renders the new Overview
// in both themes at both widths (spec R3 acceptance). Where the installation shape is known, the
// schematic must match it (spec R3.1); `null` means: only the common checks.
const PRESETS = [
  ['heat_only', { zones: ['z1'], tank: true }],
  ['cool_only', { zones: ['z1'], tank: true }],
  ['dhw_only', { zones: ['z1'], tank: true }],
  ['heat_dhw', { zones: ['z1'], tank: true }],
  ['cool_dhw', { zones: ['z1'], tank: true }],
  ['auto_heat', { zones: ['z1'], tank: true }],
  ['auto_heat_dhw', { zones: ['z1'], tank: true }],
  ['auto_cool_mode7', { zones: ['z1'], tank: true }],
  ['auto_cool_dhw', { zones: ['z1'], tank: true }],
  ['two_zones_heat_curve_cool_direct', { zones: ['z1', 'z2'], tank: true }],
  ['z1_water_z2_internal_thermostat', { zones: ['z1', 'z2'], tank: true }],
  ['zone2_only_and_thermistor', { zones: ['z2'], tank: true }],
  ['no_dhw_tank', { zones: ['z1'], tank: false }],
  ['with_extra', null],
  ['without_extra', null],
  ['pcb_active', null],
  ['pcb_inactive', null],
  ['no_integrations', null],
  ['all_integrations', null],
  ['fw-3.2.3', null],
  ['unknown-inputs', { zones: ['z1'], tank: true }], // unknown profile inputs → features shown
  ['solar_mode_3', null],
];

for (const [preset, expected] of PRESETS) {
  test.describe(`overview @ ${preset}`, () => {
    test.beforeAll(async () => { await up(preset); });
    test.afterAll(async () => { await down(); });

    for (const theme of ['day', 'night']) {
      for (const [width, height] of [[1280, 800], [390, 844]]) {
        test(`renders in ${theme} at ${width}px`, async ({ page }) => {
          const errors = watchErrors(page);
          await page.addInitScript((t) => localStorage.setItem('heishamon.theme', t), theme);
          await page.setViewportSize({ width, height });
          await openScreen(page, 'overview');
          for (const id of ['plant', 'quick-controls', 'timeline', 'recent-events', 'tiles']) {
            await expect(page.getByTestId(id)).toBeVisible();
          }
          if (expected) {
            for (const z of ['z1', 'z2']) {
              await expect(page.getByTestId(`plant-zone-${z}`)).toHaveCount(expected.zones.includes(z) ? 1 : 0);
            }
            await expect(page.getByTestId('plant-dhw-branch')).toHaveCount(expected.tank ? 1 : 0);
          }
          await noOverflow(page);
          await page.screenshot({ path: `/tmp/visual-preset-${preset}-${theme}-${width}.png`, fullPage: true });
          expect(errors).toEqual([]);
        });
      }
    }
  });
}

// profile-change switches heat → cool (and heating control → direct) after 60 s: the Overview must follow live.
test.describe('overview @ profile-change', () => {
  test.beforeAll(async () => { await up('profile-change'); });
  test.afterAll(async () => { await down(); });

  test('follows a live profile change without reload', async ({ page }) => {
    test.setTimeout(150_000);
    const errors = watchErrors(page);
    await openScreen(page, 'overview');
    // plant badge and Now panel follow the *activity* (idle while the simulated compressor is off), so the
    // profile-driven element is the mini curve, which picks the heating or cooling curve from the profile
    await expect(page.getByTestId('plant')).toBeVisible();
    await expect(page.getByTestId('mini-curve')).toContainText('Heating curve');
    await expect(page.getByTestId('mini-curve')).toContainText('Cooling curve', { timeout: 120_000 });
    expect(errors).toEqual([]);
  });
});
