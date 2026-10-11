<script>
  import { language, route } from '../lib/stores.js';
  import { translate } from '../lib/i18n/index.js';

  let { variant = 'side' } = $props();

  const items = [
    ['overview', 'common.navOverview'],
    ['charts', 'common.navCharts'],
    ['energy', 'common.navEnergy'],
    ['curve', 'common.navCurve'],
    ['settings', 'common.navSettings'],
    ['topics', 'common.navTopics'],
    ['log', 'common.navLog'],
    ['system', 'common.navSystem'],
  ];
</script>

<nav data-variant={variant} aria-label={translate($language, 'common.navLabel')}>
  {#each items as [id, key] (id)}
    <a
      href={`#/${id}`}
      data-testid={`nav-${id}`}
      aria-current={$route === id ? 'page' : undefined}
      onclick={() => route.set(id)}
    >{translate($language, key)}</a>
  {/each}
</nav>

<style>
  nav {
    display: flex;
    background: #f4f4f5;
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
  nav[data-variant='bottom'] {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    flex-wrap: wrap;
    justify-content: space-around;
    z-index: 2;
  }
</style>
