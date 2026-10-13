import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import Nav from '../src/app/Nav.svelte';
import registry, { ROUTES } from '../src/app/registry.js';
import { ROUTES as storeRoutes, parseRoute } from '../src/lib/stores.js';
import { translate } from '../src/lib/i18n/index.js';

describe('feature registry', () => {
  it('lists eight features with unique ids, orders and a component each', () => {
    expect(registry).toHaveLength(8);
    expect(new Set(registry.map((f) => f.id)).size).toBe(8);
    expect(new Set(registry.map((f) => f.order)).size).toBe(8);
    for (const f of registry) {
      expect(f.navKey).toMatch(/^common\.nav/);
      expect(f.component).toBeTruthy();
    }
  });

  it('is sorted by order and ROUTES follows it', () => {
    const orders = registry.map((f) => f.order);
    expect(orders).toEqual([...orders].sort((a, b) => a - b));
    expect(ROUTES).toEqual(registry.map((f) => f.id));
    expect(storeRoutes).toEqual(ROUTES);
    for (const id of ROUTES) expect(parseRoute(`#/${id}`)).toBe(id);
    expect(parseRoute('#/nope')).toBe('overview');
  });

  it('renders one nav link per registered feature, in order', () => {
    const { container } = render(Nav);
    const links = [...container.querySelectorAll('a')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(ROUTES.map((id) => `#/${id}`));
    expect(links.map((a) => a.textContent)).toEqual(
      registry.map((f) => translate('en', f.navKey)),
    );
  });
});
