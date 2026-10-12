import { test, expect } from '@playwright/test';
import { up, down, URL } from './stack.js';
import { commandRange, openScreen, otherThan, stateValue } from './helpers.js';

test.describe('command confirmation', () => {
  test.beforeAll(async () => { await up('heat_dhw'); });
  test.afterAll(async () => { await down(); });

  test('a setting is applied and ends confirmed', async ({ page }) => {
    await openScreen(page, 'settings');
    const control = page.getByTestId('control-SetMaxPumpDuty');
    const next = otherThan(await stateValue('main/Max_Pump_Duty'), commandRange('SetMaxPumpDuty').min, commandRange('SetMaxPumpDuty').max);
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
    const next = otherThan(await stateValue('main/Max_Pump_Duty'), commandRange('SetMaxPumpDuty').min, commandRange('SetMaxPumpDuty').max);
    await control.getByTestId('value-SetMaxPumpDuty').fill(String(next));
    await control.getByTestId('apply-SetMaxPumpDuty').click();
    await expect(control.getByTestId('command-status')).toHaveAttribute('data-status', 'failed', { timeout: 45_000 });
  });
});

test.describe('coupled setpoint (direct mode + room thermostat)', () => {
  test.beforeAll(async () => { await up('z1_water_z2_internal_thermostat'); });
  test.afterAll(async () => { await down(); });

  test('the Overview zone-2 setpoint writes the curve cold-end target, below the warm-end target', async ({ page }) => {
    // seed the state seen live in this mode (local simulator only): cold-end target below the warm-end
    // target; outside coupled mode the backend would refuse this with the ordering rule
    const res = await fetch(`${URL}/api/command`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name: 'SetCurves', value: { zone2: { heat: { target: { high: 28, low: 30 } } } }, confirm: false }),
    });
    expect(res.status).toBe(201);
    await expect.poll(async () => Number(await stateValue('main/Z2_Heat_Curve_Target_High_Temp'))).toBe(28);
    await expect.poll(async () => Number(await stateValue('main/Z2_Heat_Curve_Target_Low_Temp'))).toBe(30);

    await openScreen(page, 'overview');
    const control = page.getByTestId('control-z2-heat');
    await expect(control).toHaveAttribute('data-coupled', 'true');
    await expect(page.getByTestId('coupled-note-z2-heat')).toContainText('Z2_Heat_Curve_Target_High_Temp');
    const high = Number(await stateValue('main/Z2_Heat_Curve_Target_High_Temp'));
    const low = Number(await stateValue('main/Z2_Heat_Curve_Target_Low_Temp'));
    await expect(page.getByTestId('slider-z2-heat')).toHaveValue(String(high));
    // below the warm-end target: refused by the ordering rule outside coupled mode
    const next = Math.max(15, Math.min(low, high) - 1);
    await page.getByTestId('slider-z2-heat').fill(String(next));
    await page.getByTestId('apply-z2-heat').click();
    await expect(control.getByTestId('command-status')).toHaveAttribute('data-status', 'confirmed');
    expect(Number(await stateValue('main/Z2_Heat_Curve_Target_High_Temp'))).toBe(next);
    expect(Number(await stateValue('main/Z2_Heat_Curve_Target_Low_Temp'))).toBe(low);
    // zone 1 has a water sensor: still the request-temperature control
    await expect(page.getByTestId('control-z1-heat')).not.toHaveAttribute('data-coupled', 'true');
  });
});
