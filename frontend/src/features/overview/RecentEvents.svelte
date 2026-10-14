<script>
  import { api } from '../../lib/api.js';
  import { translate } from '../../lib/i18n/index.js';
  import { recentItems } from '../../lib/eventtext.js';

  let { lang = 'en' } = $props();
  let events = $state([]);
  let commands = $state([]);
  const TONE = { defrost: 'var(--cool)', fail: 'var(--fail)', ok: 'var(--ok)', pending: 'var(--pending)', neutral: 'var(--ink-3)' };

  $effect(() => {
    let alive = true;
    const load = () => {
      api.events({ limit: 6 }).then((b) => { if (alive) events = b?.events ?? []; }, () => {});
      api.commands({ limit: 6 }).then((b) => { if (alive) commands = b?.commands ?? []; }, () => {});
    };
    load();
    const timer = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(timer); };
  });

  const items = $derived(recentItems(events, commands, lang, 6));
  const time = (ts) => new Date(ts).toLocaleTimeString(lang === 'nl' ? 'nl-NL' : 'en-GB', { hour: '2-digit', minute: '2-digit' });
</script>

<div class="panel" data-testid="recent-events">
  <div class="panel-head"><h2>{translate(lang, 'overview.recentEvents')}</h2><a class="tag" href="#/log">{translate(lang, 'overview.openLog')} →</a></div>
  {#if items.length}
    <ul>
      {#each items as item}
        <li>
          <time class="num">{time(item.ts)}</time>
          <span class="k" style:background={TONE[item.tone]}></span>
          <div>{item.title}{#if item.detail}<small>{item.detail}</small>{/if}</div>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="empty">{translate(lang, 'overview.noEvents')}</p>
  {/if}
</div>

<style>
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: grid; grid-template-columns: 54px 16px 1fr; gap: 8px; padding: 9px 16px; border-bottom: 1px solid var(--line); font-size: 13px; }
  li:last-child { border-bottom: 0; }
  time { font-size: 12px; color: var(--ink-3); padding-top: 1px; }
  .k { width: 8px; height: 8px; border-radius: 2px; margin-top: 6px; }
  small { display: block; color: var(--ink-3); font-size: 11.5px; overflow-wrap: anywhere; }
  .empty { color: var(--ink-3); padding: 16px; margin: 0; }
  a.tag { text-decoration: none; }
</style>
