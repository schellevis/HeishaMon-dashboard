import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import catalog from '$catalog';
import App from '../src/App.svelte';
import { languages, translate } from '../src/lib/i18n/index.js';

describe('scaffold', () => {
  it('resolves $catalog to the fixture catalog', () => {
    expect(catalog.schema).toBe(1);
    expect(catalog.topics).toHaveLength(2);
  });

  it('renders the app', () => {
    render(App);
    expect(screen.getByText('HeishaMon dashboard')).toBeTruthy();
  });

  it('i18n merges with an English fallback and returns the key when unknown', () => {
    expect(languages).toEqual(['en', 'nl']);
    expect(translate('nl', 'nope.key')).toBe('nope.key');
  });
});
