/** Full `Prefs` object for `PUT /api/prefs` (spec §4.4). */

export function fullPrefs(prefs) {
  return {
    write_lock: Boolean(prefs?.write_lock),
    pcb_enabled: Boolean(prefs?.pcb_enabled),
    topic_visibility: { ...(prefs?.topic_visibility ?? {}) },
    feature_overrides: { ...(prefs?.feature_overrides ?? {}) },
    tiles: [...(prefs?.tiles ?? [])],
    chart_presets: (prefs?.chart_presets ?? []).map((preset) => ({ ...preset, topics: [...(preset.topics ?? [])] })),
  };
}
