import { test, expect } from '@playwright/test';
import { up, down } from './stack.js';
import { openScreen, otherThan, stateValue } from './helpers.js';

// Keyboard-only: elements are reached with focus()/Tab and operated with key presses; no pointer clicks.
test.describe('keyboard-only completion', () => {
  test.beforeAll(async () => { await up('heat_dhw', ['*=delay:2']); });
  test.afterAll(async () => { await down(); });

  test('settings Apply', async ({ page }) => {
    await openScreen(page, 'settings');
    const control = page.getByTestId('control-SetMaxPumpDuty');
    const next = otherThan(await stateValue('main/Max_Pump_Duty'), 0, 100);
    const input = control.getByTestId('value-SetMaxPumpDuty');
    await input.focus();
    await page.keyboard.press('Control+A');
    await page.keyboard.type(String(next));
    await page.keyboard.press('Tab');
    await expect(control.getByTestId('apply-SetMaxPumpDuty')).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(control.getByTestId('command-status')).toHaveAttribute('data-status', 'confirmed');
  });

  test('curve Apply', async ({ page }) => {
    await openScreen(page, 'curve');
    const handle = page.getByTestId('handle-cold');
    await handle.focus();
    await page.keyboard.press('ArrowUp');
    const apply = page.getByTestId('apply-curve');
    await expect(apply).toBeEnabled();
    await apply.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByTestId('confirm-dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Confirm' }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('result-curve').getByTestId('command-status').first()).toHaveAttribute('data-status', 'confirmed');
  });

  test('threshold Apply', async ({ page }) => {
    await openScreen(page, 'curve');
    await page.getByTestId('tab-z1heat').focus();
    await page.keyboard.press('Enter');
    const marker = page.getByTestId('marker-heatingOff');
    await marker.focus();
    await page.keyboard.press('ArrowRight');
    const apply = page.getByTestId('apply-heatingOff');
    await expect(apply).toBeEnabled();
    await apply.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByTestId('confirm-dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Confirm' }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('result-heatingOff').getByTestId('command-status').first()).toHaveAttribute('data-status', 'confirmed');
  });
});
