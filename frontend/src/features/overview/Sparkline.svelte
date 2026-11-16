<script>
  let { data = [], width = 100, height = 40, stroke = 'currentColor' } = $props();

  // Filter out null values for min/max calculation, but keep them in the array for positioning
  const validData = $derived(data.filter((d) => d !== null && typeof d === 'number' && !isNaN(d)));
  
  const points = $derived.by(() => {
    if (data.length === 0) return [];
    
    const validValues = validData;
    if (validValues.length === 0) return data.map(() => null);
    
    const min = Math.min(...validValues);
    const max = Math.max(...validValues);
    const range = max - min;
    const scale = range === 0 ? 1 : range;
    
    return data.map((d, i) => {
      if (d === null || typeof d !== 'number' || isNaN(d)) {
        return null; // gap
      }
      const x = data.length > 1 ? (i / (data.length - 1)) * width : 0;
      const y = height - ((d - min) / scale) * height;
      return { x, y };
    });
  });

  // Build SVG path with gaps (move command for nulls)
  const path = $derived.by(() => {
    const segments = [];
    let first = true;
    
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      if (p === null) {
        first = true; // start new segment after gap
        continue;
      }
      
      if (first) {
        segments.push(`M${p.x} ${p.y}`);
        first = false;
      } else {
        segments.push(`L${p.x} ${p.y}`);
      }
    }
    
    return segments.join(' ');
  });
</script>

<svg width="100%" {height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" data-testid="sparkline">
  <path d={path} fill="none" {stroke} stroke-width="1.5" />
</svg>
