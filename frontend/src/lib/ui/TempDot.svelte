<script>
  import { tempColor } from './thermal.js';

  let { value = null } = $props();
</script>

{#if typeof value === 'number' && Number.isFinite(value)}<i class="temp-dot" style:background={tempColor(value)} aria-hidden="true"></i>{/if}

<style>
  .temp-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
</style>
