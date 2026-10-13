import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { api, ApiError } from '../src/lib/api.js';
import { answerConfirm, commands, confirmRequest, resetClientState } from '../src/lib/stores.js';
import { createCommand } from '../src/lib/commands/controller.js';

function record(extra = {}) {
  return { id: 'c1', name: 'SetZ1HeatRequestTemperature', status: 'pending', submitted_ts: Date.now(), eeprom_warning: false, ...extra };
}

describe('command controller', () => {
  beforeEach(() => {
    resetClientState();
    vi.spyOn(api, 'command');
  });
  afterEach(() => vi.restoreAllMocks());

  it('goes idle → pending → confirmed through the commands store', async () => {
    api.command.mockResolvedValue(record());
    const cmd = createCommand('SetZ1HeatRequestTemperature');
    expect(get(cmd).status).toBe('idle');
    await cmd.submit(2);
    expect(api.command).toHaveBeenCalledWith({ name: 'SetZ1HeatRequestTemperature', value: 2, confirm: false });
    expect(get(cmd).status).toBe('pending');
    commands.update((m) => ({ ...m, c1: record({ status: 'confirmed' }) }));
    expect(get(cmd).status).toBe('confirmed');
    expect(get(cmd).record.id).toBe('c1');
  });

  it('asks for confirmation and sends nothing when declined', async () => {
    api.command.mockResolvedValue(record());
    const cmd = createCommand('SetX');
    const stop = confirmRequest.subscribe((req) => req && answerConfirm(false));
    await cmd.submit(1, { confirm: { title: 'T', body: 'B' } });
    stop();
    expect(api.command).not.toHaveBeenCalled();
    expect(get(cmd).status).toBe('idle');
  });

  it('sends confirm: true after the user accepts', async () => {
    api.command.mockResolvedValue(record());
    const cmd = createCommand('SetX');
    const stop = confirmRequest.subscribe((req) => req && answerConfirm(true));
    await cmd.submit(1, { confirm: { title: 'T', body: 'B' } });
    stop();
    expect(api.command).toHaveBeenCalledWith({ name: 'SetX', value: 1, confirm: true });
  });

  it('shows a 422 rejection code', async () => {
    api.command.mockRejectedValue(new ApiError(422, { error: 'out_of_range', message: 'x', detail: null }));
    const cmd = createCommand('SetX');
    await cmd.submit(99);
    expect(get(cmd).status).toBe('failed');
    expect(get(cmd).error).toEqual({ code: 'out_of_range', retryAfter: null });
  });

  it('shows a 429 with retry_after_s', async () => {
    api.command.mockRejectedValue(new ApiError(429, { error: 'rate_limited', message: 'x', detail: { retry_after_s: 42 } }));
    const cmd = createCommand('SetX');
    await cmd.submit(1);
    expect(get(cmd).error).toEqual({ code: 'rate_limited', retryAfter: 42 });
  });

  it('exposes the wear warning from the record eeprom_warning', async () => {
    api.command.mockResolvedValue(record({ eeprom_warning: true }));
    const cmd = createCommand('SetX');
    await cmd.submit(1);
    expect(get(cmd).warning).toBe(true);
  });

  it('clears the error with reset()', async () => {
    api.command.mockRejectedValue(new ApiError(422, { error: 'bad_type' }));
    const cmd = createCommand('SetX');
    await cmd.submit(1);
    cmd.reset();
    expect(get(cmd).error).toBeNull();
    expect(get(cmd).status).toBe('idle');
  });
});
