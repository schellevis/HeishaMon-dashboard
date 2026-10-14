import { describe, expect, it } from 'vitest';
import { commandTone, eventTone, kindLabel, recentItems } from '../src/lib/eventtext.js';

describe('eventtext', () => {
  it('labels known kinds and falls back to the raw kind', () => {
    expect(kindLabel('defrost_start', 'en')).toBe('Defrost started');
    expect(kindLabel('something_new', 'en')).toBe('something_new');
  });
  it('maps tones', () => {
    expect(eventTone('defrost_end')).toBe('defrost');
    expect(eventTone('command_rejected')).toBe('fail');
    expect(eventTone('mode_change')).toBe('neutral');
    expect(commandTone('confirmed')).toBe('ok');
    expect(commandTone('retried')).toBe('pending');
    expect(commandTone('failed')).toBe('fail');
  });
  it('merges events and commands newest first and caps the list', () => {
    const events = [{ ts: 10, kind: 'defrost_start', detail: null }, { ts: 30, kind: 'mode_change', detail: { to: 4 } }];
    const commands = [{ submitted_ts: 20, name: 'SetDHWTemp', payload: '52', status: 'confirmed' }];
    const items = recentItems(events, commands, 'en', 2);
    expect(items.map((i) => i.ts)).toEqual([30, 20]);
    expect(items[1].tone).toBe('ok');
    expect(items[1].detail).toContain('52');
  });
});
