<script>
  import { onMount } from 'svelte';
  import { translate } from '../lib/i18n/index.js';
  import { state as stateStore, profile as profileStore, prefs as prefsStore, language } from '../lib/stores.js';
  import { presentTopic } from '../lib/format.js';
  import { topicByKey } from '../lib/catalog.js';
  import { api } from '../lib/api.js';
  import Tile from '../components/overview/Tile.svelte';
  import QuickControls from '../components/overview/QuickControls.svelte';
  import { fetchSparklineValues, normalizeSparkline } from '../components/overview/sparkline.js';

  // Build the set of default tiles based on profile
  function buildDefaultTiles(profile) {
    const tiles = [];
    
    // Always include basic tiles
    tiles.push('outsideTemp');
    tiles.push('mainOutletTemp');
    tiles.push('mainInletTemp');
    tiles.push('deltaTemp');
    tiles.push('compressorFreq');
    tiles.push('heatPowerConsumption');
    tiles.push('heatPowerProduction');
    tiles.push('cop');
    tiles.push('threeWayValve');
    tiles.push('defrostingState');
    
    // DHW tile only with DHW tank
    if (profile?.dhw_installed?.value === true) {
      tiles.push('dhwTemp');
    }
    
    // Buffer tile only when configured
    if (profile?.buffer_installed?.value === true) {
      tiles.push('bufferTemp');
    }
    
    // Solar tile only when solar is active and we have extra data
    const solarMode = profile?.solar?.value;
    if (solarMode && solarMode !== 'off') {
      tiles.push('solarTemp');
    }
    
    // Cooling power only when cooling is in use
    if (profile?.cooling_in_use?.value === true) {
      tiles.push('coolPowerProduction');
    }
    
    return tiles;
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

  function getCop() {
    const consumption = getTopicFromState('main/Heat_Power_Consumption');
    const production = getTopicFromState('main/Heat_Power_Production');
    
    if (!consumption || !production || consumption.sentinel || production.sentinel) {
      return null;
    }
    
    const consVal = typeof consumption.value === 'number' ? consumption.value : null;
    const prodVal = typeof production.value === 'number' ? production.value : null;
    
    if (consVal === null || prodVal === null || consVal <= 0) return null;
    
    const copValue = prodVal / consVal;
    
    return {
      value: copValue,
      raw: String(copValue.toFixed(2)),
      kind: 'number',
      unit: '',
      decimals: 2,
      enum_label: null,
      catalogued: false,
      sentinel: false,
      last_change: Math.max(consumption.last_change, production.last_change),
      last_seen: Math.max(consumption.last_seen, production.last_seen),
      retained_only: consumption.retained_only && production.retained_only,
    };
  }

  // Map tile IDs to topic keys and labels
  const tileMap = {
    outsideTemp: { key: 'main/Outside_Temp', label: 'overview.outsideTemp' },
    mainOutletTemp: { key: 'main/Main_Outlet_Temp', label: 'overview.flowTemp' },
    mainInletTemp: { key: 'main/Main_Inlet_Temp', label: 'overview.returnTemp' },
    deltaTemp: { key: null, label: 'overview.deltaTemp', computed: true },
    compressorFreq: { key: 'main/Compressor_Freq', label: 'overview.compressorFreq' },
    heatPowerConsumption: { key: 'main/Heat_Power_Consumption', label: 'overview.powerIn' },
    heatPowerProduction: { key: 'main/Heat_Power_Production', label: 'overview.powerOut' },
    cop: { key: null, label: 'overview.cop', computed: true },
    threeWayValve: { key: 'main/ThreeWay_Valve_State', label: 'overview.threeWayValve' },
    defrostingState: { key: 'main/Defrosting_State', label: 'overview.defrost' },
    dhwTemp: { key: 'main/DHW_Temp', label: 'overview.dhwTemp' },
    bufferTemp: { key: 'main/Buffer_Temp', label: 'overview.bufferTemp' },
    solarTemp: { key: 'main/Solar_Temp', label: 'overview.solarPower' },
    coolPowerProduction: { key: 'main/Cool_Power_Production', label: 'overview.coolingPower' },
  };

  // Get sparkline values for a tile
  function getSparkline(tileId) {
    const info = tileMap[tileId];
    
    if (info.computed) {
      // Computed values don't have sparklines yet
      return [];
    }
    
    return sparklineData[tileId] ?? [];
  }

  // Get topic for a tile
  function getTileTopic(tileId) {
    const info = tileMap[tileId];
    
    if (info.computed) {
      if (tileId === 'deltaTemp') return getDeltaTemp();
      if (tileId === 'cop') return getCop();
      return null;
    }
    
    return getTopicFromState(info.key);
  }

  // Pinned tiles from prefs
  let pinnedTiles = $state($prefsStore?.tiles ?? []);

  // Active tiles (pinned + default non-pinned)
  let activeTiles = $derived([...pinnedTiles, ...buildDefaultTiles($profileStore).filter((t) => !pinnedTiles.includes(t))]);

  // Sparkline data: topic key -> array of values or null
  let sparklineData = $state({});

  // Pin/unpin handlers - persist with PUT /api/prefs
  async function handlePin(tileId) {
    if (pinnedTiles.includes(tileId)) return;
    const newTiles = [...pinnedTiles, tileId];
    try {
      await api.putPrefs({ ...$prefsStore, tiles: newTiles });
      pinnedTiles = newTiles;
    } catch (error) {
      console.warn('Failed to save pinned tiles:', error);
    }
  }

  async function handleUnpin(tileId) {
    const newTiles = pinnedTiles.filter((t) => t !== tileId);
    try {
      await api.putPrefs({ ...$prefsStore, tiles: newTiles });
      pinnedTiles = newTiles;
    } catch (error) {
      console.warn('Failed to save unpinned tiles:', error);
    }
  }

  // Load sparklines when state/profile are available
  let loadingSparklines = $state(false);

  $effect(() => {
    if ($stateStore && $profileStore && activeTiles.length > 0 && !loadingSparklines) {
      loadingSparklines = true;
      
      const now = Date.now();
      const twentyFourHoursAgo = now - 24 * 60 * 60 * 1000;
      
      Promise.all(
        activeTiles.map(async (tileId) => {
          const info = tileMap[tileId];
          if (info.computed) {
            sparklineData[tileId] = [];
            return;
          }
          
          if (info.key) {
            try {
              const values = await fetchSparklineValues(info.key, now);
              sparklineData[tileId] = values;
            } catch (error) {
              sparklineData[tileId] = [];
            }
          }
        })
      ).finally(() => {
        loadingSparklines = false;
      });
    }
  });
</script>

<div class="overview" data-testid="screen-overview">
  {#if $stateStore && $profileStore}
    <QuickControls profile={$profileStore} stateData={$stateStore} prefs={$prefsStore} lang={$language} />

    <div class="tiles" data-testid="tiles">
      {#each activeTiles as tileId}
        {@const info = tileMap[tileId]}
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
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
  }
  .loading {
    color: #888;
  }
</style>
