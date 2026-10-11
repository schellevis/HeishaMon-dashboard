import { test, expect } from '@playwright/test';
import { up, down } from './stack.js';
import { openScreen, otherThan, stateValue } from './helpers.js';

test.describe('command confirmation', () => {
  test.beforeAll(async () => { await up('heat_dhw'); });
  test.afterAll(async () => { await down(); });

  test('a setting is applied and ends confirmed', async ({ page }) => {
    await openScreen(page, 'settings');
    const control = page.getByTestId('control-SetMaxPumpDuty');
    const next = otherThan(await stateValue('main/Max_Pump_Duty'), 0, 100);
    await control.getByTestId('value-SetMaxPumpDuty').fill(String(next));
    await control.getByTestId('apply-SetMaxPumpDuty').click();
    await expect(control.getByTestId('command-status')).toHaveAttribute('data-status', 'confirmed');
  });
});

test.describe('dropped command', () => {
  test.beforeAll(async () => { await up('heat_dhw', ['SetMaxPumpDuty=drop']); });
  test.afterAll(async () => { await down(); });

  test('a dropped command ends failed after retry', async ({ page }) => {
    test.setTimeout(90_000);
    await openScreen(page, 'settings');
    const control = page.getByTestId('control-SetMaxPumpDuty');
    const next = otherThan(await stateValue('main/Max_Pump_Duty'), 0, 100);
    await control.getByTestId('value-SetMaxPumpDuty').fill(String(next));
    await control.getByTestId('apply-SetMaxPumpDuty').click();
    await expect(control.getByTestId('command-status')).toHaveAttribute('data-status', 'failed', { timeout: 45_000 });
  });
});
