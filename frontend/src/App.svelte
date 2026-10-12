<script>
  import { onMount } from 'svelte';
  import ConfirmDialog from './components/ConfirmDialog.svelte';
  import Nav from './components/Nav.svelte';
  import Statusbar from './components/Statusbar.svelte';
  import { translate } from './lib/i18n/index.js';
  import Charts from './screens/Charts.svelte';
  import Curve from './screens/Curve.svelte';
  import Energy from './screens/Energy.svelte';
  import Log from './screens/Log.svelte';
  import Overview from './screens/Overview.svelte';
  import Settings from './screens/Settings.svelte';
  import System from './screens/System.svelte';
  import Topics from './screens/Topics.svelte';
  import {
    answerConfirm,
    bindLanguagePersistence,
    confirmRequest,
    language,
    loadLanguage,
    route,
    setRouteFromHash,
    startRealtime,
  } from './lib/stores.js';

  let desktop = $state(typeof window !== 'undefined' && window.innerWidth >= 768);

  const screens = {
    overview: Overview,
    charts: Charts,
    energy: Energy,
    curve: Curve,
    settings: Settings,
    topics: Topics,
    log: Log,
    system: System,
  };

  let Screen = $derived(screens[$route] ?? Overview);
  let navVariant = $derived(desktop ? 'side' : 'bottom');

  onMount(() => {
    loadLanguage();
    const unbind = bindLanguagePersistence();
    const sync = () => {
      desktop = window.innerWidth >= 768;
      setRouteFromHash(location.hash);
    };
    sync();
    window.addEventListener('resize', sync);
    window.addEventListener('hashchange', sync);
    const stop = import.meta.env.MODE === 'test' ? () => {} : startRealtime();
    return () => {
      unbind();
      window.removeEventListener('resize', sync);
      window.removeEventListener('hashchange', sync);
      stop();
    };
  });
</script>

<div class="app" data-testid="shell" data-layout={navVariant}>
  <header>
    <h1>HeishaMon dashboard</h1>
    <Statusbar />
  </header>
  <div class="frame" data-layout={navVariant}>
    <Nav variant={navVariant} />
    <main>
      <Screen />
    </main>
  </div>
  <ConfirmDialog
    open={$confirmRequest !== null}
    title={$confirmRequest?.title ?? translate($language, 'common.confirmTitle')}
    body={$confirmRequest?.body ?? translate($language, 'common.confirmBody')}
    confirmLabel={translate($language, 'common.confirm')}
    cancelLabel={translate($language, 'common.cancel')}
    onconfirm={() => answerConfirm(true)}
    oncancel={() => answerConfirm(false)}
  />
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, sans-serif;
  }
  :global(.value-stale) {
    color: #6b7280;
  }
  .app {
    min-height: 100vh;
    max-width: 100%;
    display: flex;
    flex-direction: column;
  }
  header {
    min-width: 0;
  }
  h1 {
    font-size: 1.125rem;
    margin: 0;
    padding: 0.75rem 1rem 0;
  }
  .frame {
    display: flex;
    flex: 1;
    min-width: 0;
  }
  .frame[data-layout='bottom'] {
    flex-direction: column;
  }
  main {
    flex: 1;
    min-width: 0;
    padding: 1rem;
  }
</style>
