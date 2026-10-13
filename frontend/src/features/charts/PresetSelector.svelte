<script module>
  import { powerPairs } from '../../lib/domain/power.js';

  /** Built-in presets. Every key is a catalog key. Power topics follow the installation profile
   * (`power: true`); COP is computed client-side and is not a topic. */
  export const BUILTIN_PRESETS = {
    temperatures: {
      name: 'preset_temperatures',
      topics: [
        'main/Outside_Temp',
        'main/Main_Outlet_Temp',
        'main/Main_Inlet_Temp',
        'main/Z1_Water_Temp',
        'main/Z2_Water_Temp',
        'main/Z1_Water_Target_Temp',
        'main/Z2_Water_Target_Temp',
        'main/Room_Thermostat_Temp',
      ],
      builtin: true,
    },
    power_cop: {
      name: 'preset_power_cop',
      topics: ['main/Compressor_Freq'],
      power: true,
      builtin: true,
    },
    compressor: {
      name: 'preset_compressor',
      topics: ['main/Compressor_Freq', 'main/Compressor_Current', 'main/Heatpump_State', 'main/Defrosting_State'],
      builtin: true,
    },
    pump_pressure: {
      name: 'preset_pump_pressure',
      topics: ['main/Pump_Flow', 'main/Pump_Speed', 'main/High_Pressure', 'main/Low_Pressure'],
      builtin: true,
    },
    dhw: {
      name: 'preset_dhw',
      topics: ['main/DHW_Temp', 'main/DHW_Target_Temp', 'main/DHW_Heater_State', 'main/ThreeWay_Valve_State'],
      builtin: true,
    },
    zones: {
      name: 'preset_zones',
      topics: [
        'main/Z1_Heat_Request_Temp',
        'main/Z2_Heat_Request_Temp',
        'main/Z1_Water_Temp',
        'main/Z2_Water_Temp',
        'main/Room_Thermostat_Temp',
      ],
      builtin: true,
    },
    cooling: {
      name: 'preset_cooling',
      topics: ['main/Z1_Cool_Request_Temp', 'main/Z2_Cool_Request_Temp', 'main/Operating_Mode_State'],
      builtin: true,
    },
  };

  /** Topic keys of a preset for a profile (power presets add the profile's heat/cool/DHW power pairs). */
  export function presetTopics(preset, profile) {
    if (!preset.power) return preset.topics;
    const pairs = Object.values(powerPairs(profile).pairs).flat();
    return [...preset.topics, ...pairs];
  }
</script>

<script>
  import { translate } from '../../lib/i18n/index.js';
  import { prefs, language, updatePrefs } from '../../lib/stores.js';
  import { catalog } from '../../lib/catalog.js';
  import { profile } from '../../lib/stores.js';
  
  /**
   * Preset selector component
   * Allows users to select and manage chart presets
   */
  
  // Props are automatically available in Svelte 5
  let { selectedTopics, onSelectPreset, onTopicsChange } = $props();
  
  // User presets from prefs
  let userPresets = $derived($prefs?.chart_presets || []);
  
  // Current preset name input
  let presetNameInput = $state('');
  
  // Error message
  let error = $state(null);
  
  // Filter built-in presets based on profile
  let filteredBuiltinPresets = $derived(filterPresetsByProfile(Object.values(BUILTIN_PRESETS)));
  
  function filterPresetsByProfile(presets) {
    const filtered = [];
    
    for (const preset of presets) {
      // Check each topic in the preset
      const relevantTopics = presetTopics(preset, $profile).filter(topicKey => {
        // Check if topic exists in catalog
        const catalogTopic = catalog.topics.find(t => t.key === topicKey);
        if (!catalogTopic) return false;
        
        // Check if topic is relevant for current profile
        if ($profile) {
          return isTopicRelevant(catalogTopic);
        }
        
        return true;
      });
      
      // Only include preset if it has at least one relevant topic
      if (relevantTopics.length > 0) {
        filtered.push({
          ...preset,
          topics: relevantTopics,
        });
      }
    }
    
    return filtered;
  }
  
  // Check if a topic is relevant based on profile
  function isTopicRelevant(topic) {
    return !(topic.feature && $prefs?.feature_overrides?.[topic.feature] === 'hide');
  }
  
  // Select a preset
  function selectPreset(preset) {
    error = null;
    
    // Check if any topics in the preset are ignored
    const topicVisibility = $prefs?.topic_visibility || {};
    const availableTopics = preset.topics.filter(key => {
      const visibility = topicVisibility[key] || 'visible';
      return visibility !== 'ignored';
    });
    
    if (availableTopics.length === 0) {
      error = translate($language, 'charts.no_topics_selected');
      return;
    }
    
    onSelectPreset(availableTopics);
  }
  
  // Save current selection as a preset
  async function saveCurrentPreset() {
    if (!presetNameInput.trim()) {
      error = 'Please enter a preset name';
      return;
    }
    
    // Check if preset name already exists
    const existingUser = userPresets.find(p => p.name === presetNameInput);
    if (existingUser) {
      error = 'A preset with this name already exists';
      return;
    }
    
    // Check if preset name exists in builtins
    const existingBuiltin = Object.values(BUILTIN_PRESETS).find(p => 
      translate($language, 'charts.' + p.name) === presetNameInput
    );
    if (existingBuiltin) {
      error = 'This name is reserved for a built-in preset';
      return;
    }
    
    // Create new preset
    const newPreset = {
      name: presetNameInput,
      topics: [...selectedTopics],
    };
    
    try {
      // Update prefs
      const currentPrefs = $prefs;
      const updatedPresets = [...(currentPrefs.chart_presets || []), newPreset];
      
      await updatePrefs({ chart_presets: updatedPresets });
      
      // Update local state
      userPresets = updatedPresets;
      presetNameInput = '';
      error = null;
    } catch (err) {
      error = err.message || 'Failed to save preset';
    }
  }
  
  // Delete a user preset
  async function deleteUserPreset(preset) {
    try {
      const updatedPresets = userPresets.filter(p => p !== preset);
      
      await updatePrefs({ chart_presets: updatedPresets });
      
      userPresets = updatedPresets;
      error = null;
    } catch (err) {
      error = err.message || 'Failed to delete preset';
    }
  }
  
  // Get display name for preset
  function getPresetDisplayName(preset) {
    if (preset.builtin) {
      return translate($language, 'charts.' + preset.name);
    }
    return preset.name;
  }
</script>

<div class="preset-selector">
  <h4>{translate($language, 'charts.presets_label')}</h4>
  
  <div class="save-preset">
    <h5>{translate($language, 'charts.save_preset_label')}</h5>
    <div class="save-form">
      <input
        type="text"
        bind:value={presetNameInput}
        placeholder={translate($language, 'charts.preset_name_placeholder')}
      />
      <button onclick={saveCurrentPreset}>
        {translate($language, 'charts.save_preset_button')}
      </button>
    </div>
    {#if error}
      <div class="error">{error}</div>
    {/if}
  </div>
  
  <div class="preset-list">
    {#each filteredBuiltinPresets as preset}
      <button onclick={() => selectPreset(preset)}>
        {getPresetDisplayName(preset)}
      </button>
    {/each}
  </div>
  
  {#if userPresets.length > 0}
    <div class="user-presets">
      <h5>User Presets</h5>
      <div class="preset-list">
        {#each userPresets as preset}
          <div class="user-preset">
            <button onclick={() => selectPreset(preset)}>
              {preset.name}
            </button>
            <button onclick={() => deleteUserPreset(preset)} class="delete" title="Delete">
              ×
            </button>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .preset-selector {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    padding: 12px;
  }
  
  .preset-selector h4 {
    margin: 0 0 12px 0;
    font-size: 14px;
  }
  
  .preset-selector h5 {
    margin: 12px 0 8px 0;
    font-size: 12px;
    color: var(--text-secondary);
  }
  
  .preset-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  
  .preset-list button {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
  }
  
  .preset-list button:hover {
    background: var(--bg-hover);
  }
  
  .user-presets {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  
  .user-preset {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  
  .user-preset .delete {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 2px 4px;
    font-size: 14px;
  }
  
  .user-preset .delete:hover {
    color: var(--error);
  }
  
  .save-preset {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  
  .save-form {
    display: flex;
    gap: 8px;
  }
  
  .save-form input {
    flex: 1;
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    font-size: 12px;
  }
  
  .save-form button {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--primary);
    color: white;
    cursor: pointer;
    font-size: 12px;
  }
  
  .save-form button:hover {
    background: var(--primary-dark);
  }
  
  .error {
    margin-top: 8px;
    color: var(--error);
    font-size: 12px;
  }
</style>
