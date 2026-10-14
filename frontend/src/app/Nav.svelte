<script>
  import { language, route } from '../lib/stores.js';
  import registry from './registry.js';
  import { iconFor } from './icons.js';
  import { translate } from '../lib/i18n/index.js';

  let { variant = 'side' } = $props();
  // Log and System are reference screens: bottom of the rail on desktop.
  const isTail = (f) => f.order >= 7;
</script>

<nav data-variant={variant} aria-label={translate($language, 'common.navLabel')}>
  {#if variant === 'side'}
    <svg class="mark" viewBox="0 0 36 36" aria-hidden="true">
      <rect x="1" y="1" width="34" height="34" rx="9" fill="none" stroke="var(--line-2)" />
      <path d="M8 22 C 12 12, 16 12, 18 18 S 24 24, 28 14" fill="none" stroke="var(--warm)" stroke-width="2.4" stroke-linecap="round" />
      <circle cx="28" cy="14" r="2.6" fill="var(--warm)" />
    </svg>
  {/if}
  {#each registry as feature (feature.id)}
    {#if variant === 'side' && isTail(feature) && registry.find(isTail) === feature}<span class="spacer"></span>{/if}
    <a
      href={`#/${feature.id}`}
      data-testid={`nav-${feature.id}`}
      aria-current={$route === feature.id ? 'page' : undefined}
      onclick={() => route.set(feature.id)}
    ><svg viewBox="0 0 24 24" aria-hidden="true"><path d={iconFor(feature.id)} /></svg>{translate($language, feature.navKey)}</a>
  {/each}
</nav>

<style>
  nav { display: flex; background: var(--panel); min-width: 0; }
  a {
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    color: var(--ink-3); text-decoration: none; font-size: 11px; border-radius: 8px; padding: 8px 0;
  }
  a svg { width: 20px; height: 20px; stroke: currentColor; fill: none; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
  a:hover { color: var(--ink); background: var(--panel-2); }
  a[aria-current='page'] { color: var(--ink); background: var(--panel-2); }
  .mark { width: 36px; height: 36px; margin-bottom: 14px; }
  .spacer { flex: 1; }
  nav[data-variant='side'] {
    flex-direction: column; align-items: center; gap: 4px; width: 76px; flex: none;
    padding: 14px 0; border-right: 1px solid var(--line);
    position: sticky; top: 0; height: 100vh; box-sizing: border-box;
  }
  nav[data-variant='side'] a { width: 64px; text-align: center; }
  nav[data-variant='side'] a[aria-current='page'] { box-shadow: inset 2px 0 0 var(--warm); }
  nav[data-variant='bottom'] {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 10;
    border-top: 1px solid var(--line); overflow-x: auto; scrollbar-width: none;
    padding: 4px 4px calc(4px + env(safe-area-inset-bottom));
  }
  nav[data-variant='bottom'] a { flex: 1 0 64px; font-size: 10.5px; white-space: nowrap; }
  nav[data-variant='bottom'] a[aria-current='page'] { box-shadow: inset 0 2px 0 var(--warm); }
</style>
