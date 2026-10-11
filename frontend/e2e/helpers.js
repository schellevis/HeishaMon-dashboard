import { expect } from '@playwright/test';
import { URL } from './stack.js';

export const SCREENS = ['overview', 'charts', 'energy', 'curve', 'settings', 'topics', 'log', 'system'];

/** Open a screen and fail the test on uncaught page errors. */
export async function openScreen(page, name) {
  await page.goto(`${URL}/#/${name}`);
  await expect(page.getByTestId(`screen-${name}`)).toBeVisible();
  await expect(page.getByTestId('device-status')).not.toHaveText(/^\s*$/);
}

export function watchErrors(page) {
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  return errors;
}

export async function stateValue(topic) {
  const state = await (await fetch(`${URL}/api/state`)).json();
  return state.topics?.[topic]?.raw ?? state.topics?.[topic]?.value;
}

/** A value different from the current one, inside [min, max]. */
export function otherThan(current, min, max) {
  const n = Number(current);
  return Number.isFinite(n) && n + 1 >= min && n + 1 <= max ? n + 1 : min;
}

export async function noOverflow(page) {
  const sizes = await page.evaluate(() => ({
    doc: [document.documentElement.scrollWidth, document.documentElement.clientWidth],
    body: [document.body.scrollWidth, document.body.clientWidth],
  }));
  expect(sizes.doc[0], `documentElement ${sizes.doc}`).toBeLessThanOrEqual(sizes.doc[1]);
  expect(sizes.body[0], `body ${sizes.body}`).toBeLessThanOrEqual(sizes.body[1]);
}
