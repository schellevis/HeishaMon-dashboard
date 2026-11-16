<script>
  import { onMount } from 'svelte';
  import ConfirmDialog from '../lib/ui/ConfirmDialog.svelte';
  import Nav from './Nav.svelte';
  import Statusbar from './Statusbar.svelte';
  import registry from './registry.js';
  import { translate } from '../lib/i18n/index.js';
  import {
    answerConfirm,
    bindLanguagePersistence,
    confirmRequest,
    language,
    loadLanguage,
    route,
    setRouteFromHash,
    startRealtime,
  } from '../lib/stores.js';

  let desktop = $state(typeof window !== 'undefined' && window.innerWidth >= 760);

  const screens = Object.fromEntries(registry.map((feature) => [feature.id, feature.component]));

  let Screen = $derived(screens[$route] ?? screens.overview);
  let navVariant = $derived(desktop ? 'side' : 'bottom');

  onMount(() => {
    loadLanguage();
    const unbind = bindLanguagePersistence();
    const sync = () => {
      desktop = window.innerWidth >= 760;
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
  <Nav variant={navVariant} />
  <div class="column">
    <h1 class="sr-only">{translate($language, 'common.brand')}</h1>
    <Statusbar />
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
  .app { min-height: 100vh; display: flex; }
  .app[data-layout='bottom'] { display: block; }
  .column { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  main { flex: 1; min-width: 0; padding: 22px 24px 48px; }
  .app[data-layout='bottom'] main { padding: 16px 12px 96px; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
