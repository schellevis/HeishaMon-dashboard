import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import TopicRow from '../src/features/topics/TopicRow.svelte';

const tv = (value, raw, sentinel) => ({ value, raw, sentinel, kind: 'number', unit: '°C', decimals: 1, enum_label: null, catalogued: true, last_change: 1, last_seen: 1, retained_only: false });
const cat = { unit: '°C', label: { en: 'Temperature', nl: 'Temperatuur' } };

describe('TopicRow', () => {
  it('shows a sentinel as a badge with its meaning', () => {
    render(TopicRow, { topicKey: 'main/Buffer_Temp', topicValue: tv(-128, '-128', true), catalogTopic: cat, lang: 'en', now: 2 });
    expect(screen.getByTestId('sentinel-main/Buffer_Temp').textContent).toBe('-128 · sensor absent');
  });
  it('marks a temperature with a ramp dot', () => {
    const { container } = render(TopicRow, { topicKey: 'main/Outside_Temp', topicValue: tv(6, '6', false), catalogTopic: cat, lang: 'en', now: 2 });
    expect(container.querySelector('.temp-dot')).not.toBeNull();
  });
});
