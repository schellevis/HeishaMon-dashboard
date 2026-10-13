<script>
  import { language, route } from '../lib/stores.js';
  import registry from './registry.js';
  import { translate } from '../lib/i18n/index.js';

  let { variant = 'side' } = $props();

</script>

<nav data-variant={variant} aria-label={translate($language, 'common.navLabel')}>
  {#each registry as { id, navKey } (id)}
    <a
      href={`#/${id}`}
      data-testid={`nav-${id}`}
      aria-current={$route === id ? 'page' : undefined}
      onclick={() => route.set(id)}
    >{translate($language, navKey)}</a>
  {/each}
</nav>

<style>
  nav {
    display: flex;
    background: var(--bg-secondary);
    min-width: 0;
  }
  a {
    color: inherit;
    text-decoration: none;
    padding: 0.5rem 0.75rem;
  }
  a[aria-current='page'] {
    font-weight: 700;
  }
  nav[data-variant='side'] {
    flex-direction: column;
    width: 11rem;
    flex: none;
  }
  /* Narrow screens: one sticky, horizontally scrollable tab row at the top of the content. */
  nav[data-variant='bottom'] {
    position: sticky;
    top: 0;
    z-index: 5;
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
    border-bottom: 1px solid var(--border);
  }
  nav[data-variant='bottom'] a {
    flex: none;
    white-space: nowrap;
    padding: 0.625rem 0.75rem;
  }
  nav[data-variant='bottom'] a[aria-current='page'] {
    box-shadow: inset 0 -2px 0 var(--primary);
  }
</style>
