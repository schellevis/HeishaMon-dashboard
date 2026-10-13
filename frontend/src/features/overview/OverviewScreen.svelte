<script>
  import { onMount } from 'svelte';
  import { translate } from '../../lib/i18n/index.js';
  import { state as stateStore, profile as profileStore, prefs as prefsStore, commands as commandsStore, language, updatePrefs } from '../../lib/stores.js';
  import { presentTopic } from '../../lib/format.js';
  import { topicByKey } from '../../lib/catalog.js';
  import { api } from '../../lib/api.js';
  import Tile from './Tile.svelte';
  import QuickControls from './QuickControls.svelte';
  import { liveCop, powerPairs } from '../../lib/domain/power.js';
  import { tileIds } from '../../lib/domain/rules.js';
  import { fetchSparklineValues, normalizeSparkline } from './sparkline.js';

  // Default tiles: every built-in id from rules.json, minus those the profile rules out
  const TILE_CONDITIONS = {
    dhwTemp: (profile) => profile?.dhw_installed?.value === true,
    bufferTemp: (profile) => profile?.buffer_installed?.value === true,
    solarTemp: (profile) => {
      const solarMode = profile?.solar?.value;
      return Boolean(solarMode) && solarMode !== 'off';
    },
    coolPowerProduction: (profile) => profile?.cooling_in_use?.value === true,
  };

  function buildDefaultTiles(profile) {
    return tileIds.filter((id) => (TILE_CONDITIONS[id] ? TILE_CONDITIONS[id](profile) : true));
  }

  // Build topic value from state
  function getTopicFromState(topicKey) {
    return $stateStore.topics?.[topicKey] ?? null;
  }

  // Compute derived values
  function getDeltaTemp() {
    const outlet = getTopicFromState('main/Main_Outlet_Temp');
    const inlet = getTopicFromState('main/Main_Inlet_Temp');
    
    if (!outlet || !inlet || outlet.sentinel || inlet.sentinel) {
      return null;
    }
    
    const outVal = typeof outlet.value === 'number' ? outlet.value : null;
    const inVal = typeof inlet.value === 'number' ? inlet.value : null;
    
    if (outVal === null || inVal === null) return null;
    
    return {
      value: outVal - inVal,
      raw: String(outVal - inVal),
      kind: 'number',
      unit: '°C',
      decimals: 1,
      enum_label: null,
      catalogued: false,
      sentinel: false,
      last_change: Math.max(outlet.last_change, inlet.last_change),
      last_seen: Math.max(outlet.last_seen, inlet.last_seen),
      retained_only: outlet.retained_only && inlet.retained_only,
    };
  }

  // Map tile IDs to topic keys and labels
  const tileMap = {
    outsideTemp: { key: 'main/Outside_Temp', label: 'overview.outsideTemp' },
    mainOutletTemp: { key: 'main/Main_Outlet_Temp', label: 'overview.flowTemp' },
    mainInletTemp: { key: 'main/Main_Inlet_Temp', label: 'overview.returnTemp' },
    deltaTemp: { key: null, label: 'overview.deltaTemp', computed: true },
    compressorFreq: { key: 'main/Compressor_Freq', label: 'overview.compressorFreq' },
    heatPowerConsumption: { key: null, label: 'overview.powerIn', power: 1 },
    heatPowerProduction: { key: null, label: 'overview.powerOut', power: 0 },
    cop: { key: null, label: 'overview.cop', computed: true },
    threeWayValve: { key: 'main/ThreeWay_Valve_State', label: 'overview.threeWayValve' },
    defrostingState: { key: 'main/Defrosting_State', label: 'overview.defrost' },
    dhwTemp: { key: 'main/DHW_Temp', label: 'overview.dhwTemp' },
    bufferTemp: { key: 'main/Buffer_Temp', label: 'overview.bufferTemp' },
    solarTemp: { key: 'main/Solar_Temp', label: 'overview.solarPower' },
    coolPowerProduction: { key: null, label: 'overview.coolingPower', cool: true },
  };

  // A stored tile is a built-in id or a catalogued topic key; anything else is skipped.
  function infoOf(tileId) {
    if (Object.hasOwn(tileMap, tileId)) return tileMap[tileId];
    return topicByKey(tileId) ? { key: tileId } : null;
  }

  // Get sparkline values for a tile
  function getSparkline(tileId) {
    const info = infoOf(tileId);
    
    if (info.computed) {
      // Computed values don't have sparklines yet
      return [];
    }
    
    return sparklineData[tileId] ?? [];
  }

  // Topic key of a stored tile: power tiles follow the profile (extra/ vs main/)
  function tileKey(tileId, profile) {
    const info = infoOf(tileId);
    if (info.power !== undefined) return powerPairs(profile).pairs.heat[info.power];
    if (info.cool) return powerPairs(profile).pairs.cool[0];
    return info.key;
  }

  // Get topic for a tile
  function getTileTopic(tileId) {
    const info = infoOf(tileId);
    
    if (info.computed) {
      if (tileId === 'deltaTemp') return getDeltaTemp();
      if (tileId === 'cop') return liveCop($stateStore.topics, $profileStore);
      return null;
    }
    
    return getTopicFromState(tileKey(tileId, $profileStore));
  }

  // Pinned tiles come from the shared prefs store, so an update from elsewhere shows up here
  const pinnedTiles = $derived($prefsStore?.tiles ?? []);

  // Active tiles (pinned + default non-pinned)
  let activeTiles = $derived(
    [...pinnedTiles, ...buildDefaultTiles($profileStore).filter((t) => !pinnedTiles.includes(t))].filter((id) =>
      infoOf(id) !== null,
    ),
  );

  // Sparkline data: topic key -> array of values or null
  let sparklineData = $state({});

  // Pin/unpin handlers - persist with PUT /api/prefs
  async function handlePin(tileId) {
    if (pinnedTiles.includes(tileId)) return;
    const newTiles = [...pinnedTiles, tileId];
    try {
      await updatePrefs({ tiles: newTiles });
    } catch (error) {
      console.warn('Failed to save pinned tiles:', error);
    }
  }

  async function handleUnpin(tileId) {
    const newTiles = pinnedTiles.filter((t) => t !== tileId);
    try {
      await updatePrefs({ tiles: newTiles });
    } catch (error) {
      console.warn('Failed to save unpinned tiles:', error);
    }
  }

  // Sparklines: fetched once per tile set and refreshed every 5 minutes — never per live message.
  const SPARKLINE_REFRESH_MS = 5 * 60 * 1000;
  const ready = $derived(Boolean($stateStore && $profileStore));
  const sparklineKeys = $derived(activeTiles.filter((id) => !infoOf(id).computed).join('|'));
  const sparklineTopics = $derived(Object.fromEntries(activeTiles.filter((id) => !infoOf(id).computed).map((id) => [id, tileKey(id, $profileStore)])));

  $effect(() => {
    const ids = sparklineKeys ? sparklineKeys.split('|') : [];
    if (!ready || !ids.length) return undefined;
    let alive = true;
    const load = async () => {
      const now = Date.now();
      const next = {};
      await Promise.all(ids.map(async (tileId) => {
        try {
          next[tileId] = await fetchSparklineValues(sparklineTopics[tileId], now);
        } catch {
          next[tileId] = [];
        }
      }));
      if (alive) sparklineData = next;
    };
    load();
    const timer = setInterval(load, SPARKLINE_REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  });
</script>

<div class="overview" data-testid="screen-overview">
  {#if $stateStore && $profileStore}
    <QuickControls profile={$profileStore} stateData={$stateStore} prefs={$prefsStore} lang={$language} commandMap={$commandsStore} />

    <div class="tiles" data-testid="tiles">
      {#each activeTiles as tileId}
        {@const topic = getTileTopic(tileId)}
        {@const sparkline = getSparkline(tileId)}
        <Tile
          key={tileId}
          topic={topic}
          sparkline={sparkline}
          lang={$language}
          deviceOnline={$stateStore.device_online}
          isPinned={pinnedTiles.includes(tileId)}
          onPin={handlePin}
          onUnpin={handleUnpin}
        />
      {/each}
    </div>
  {:else}
    <p class="loading">{translate($language, 'common.ageUnknown')}</p>
  {/if}
</div>

<style>
  .overview {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(10.5rem, 45%), 1fr));
    gap: 0.75rem;
  }
  .loading {
    color: #888;
  }
</style>
