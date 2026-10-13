<script>
  let { points = [] } = $props();

  const path = $derived.by(() => {
    const series = points.filter((value) => typeof value === 'number' && Number.isFinite(value));
    if (!series.length) return '';
    const min = Math.min(...series);
    const max = Math.max(...series);
    const span = max - min || 1;
    return series.map((value, index) => {
      const x = series.length === 1 ? 0 : (index / (series.length - 1)) * 100;
      const y = 20 - ((value - min) / span) * 20;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
  });
</script>

<svg data-testid="topic-sparkline" viewBox="0 0 100 20" width="100" height="20" aria-hidden="true">
  {#if path}<path d={path} fill="none" stroke="currentColor" />{/if}
</svg>
