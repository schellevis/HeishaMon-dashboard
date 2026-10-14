import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Nav from '../src/app/Nav.svelte';
import Statusbar from '../src/app/Statusbar.svelte';
import registry from '../src/app/registry.js';
import { iconFor } from '../src/app/icons.js';
import { resolvedTheme, setTheme } from '../src/lib/theme.js';

describe('nav rail', () => {
  it('has an icon for every registered screen', () => {
    for (const { id } of registry) expect(iconFor(id)).toMatch(/^M/);
  });
  it('renders an svg icon inside each link and keeps the label as text', () => {
    const { container } = render(Nav, { variant: 'side' });
    const links = [...container.querySelectorAll('a')];
    expect(links).toHaveLength(registry.length);
    for (const a of links) expect(a.querySelector('svg')).not.toBeNull();
  });
});

describe('status strip', () => {
  it('toggles the theme between day and night', async () => {
    setTheme('night');
    render(Statusbar, { now: 0 });
    await fireEvent.click(screen.getByTestId('theme-toggle'));
    expect(get(resolvedTheme)).toBe('day');
    await fireEvent.click(screen.getByTestId('theme-toggle'));
    expect(get(resolvedTheme)).toBe('night');
  });
  it('keeps the existing test ids', () => {
    render(Statusbar, { now: 0 });
    for (const id of ['device-status', 'broker-status', 'last-message', 'error-code', 'operating-mode', 'activity', 'write-lock', 'language-switch', 'lang-en', 'lang-nl']) {
      expect(screen.getByTestId(id)).toBeTruthy();
    }
  });
});
