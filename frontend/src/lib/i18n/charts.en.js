/** English strings for the Charts screen */
export default {
  // Screen title
  charts_title: "Charts",
  
  // Presets
  presets_label: "Presets",
  save_preset_label: "Save current selection as preset",
  preset_name_placeholder: "Preset name",
  save_preset_button: "Save",
  delete_preset_button: "Delete",
  
  // Built-in preset names
  preset_temperatures: "Temperatures",
  preset_power_cop: "Power & COP",
  preset_compressor: "Compressor",
  preset_pump_pressure: "Pump & Pressure",
  preset_dhw: "DHW",
  preset_zones: "Zones",
  preset_cooling: "Cooling",
  
  // Topic selection
  add_topic_label: "Add topic",
  available_topics_label: "Available topics",
  selected_topics_label: "Selected topics",
  no_topics_selected: "No topics selected",
  filter_topics_placeholder: "Filter topics...",
  
  // Time range
  time_range_label: "Time range",
  zoom_in: "Zoom in",
  zoom_out: "Zoom out",
  pan_left: "Pan left",
  pan_right: "Pan right",
  
  // Range presets
  range_1h: "1 hour",
  range_6h: "6 hours",
  range_12h: "12 hours",
  range_1d: "1 day",
  range_3d: "3 days",
  range_1w: "1 week",
  range_1m: "1 month",
  range_3m: "3 months",
  range_1y: "1 year",
  range_custom: "Custom",
  
  // Resolution
  resolution_label: "Resolution",
  resolution_auto: "Auto",
  resolution_raw: "Raw",
  resolution_1m: "1 minute",
  resolution_1h: "1 hour",
  
  // CSV export
  csv_export_label: "Export to CSV",
  
  // Axis labels
  x_axis_label: "Time",
  y_axis_label: "Value",
  
  // Chart types
  chart_line: "Line",
  chart_band: "Band",
  
  // Status
  loading: "Loading...",
  no_data: "No data available for the selected range",
  partial_data: "Partial data (limited to {count} points)",
  
  // Enum band labels - these should match the catalog enum labels
  // These are used as fallbacks when catalog labels are not available
  enum_off: "Off",
  enum_on: "On",
  enum_idle: "Idle",
  enum_heating: "Heating",
  enum_cooling: "Cooling",
  enum_dhw: "DHW",
  enum_defrost: "Defrost",
  
  // Tooltips
  tooltip_time: "Time: {time}",
  tooltip_value: "{label}: {value}",
  
  // Actions
  clear_selection: "Clear selection",
  reset_zoom: "Reset zoom",
  
  // Profile filtering
  profile_filter_label: "Filter by profile",
  show_all: "Show all",
  show_relevant: "Show relevant only",
  
  // Visibility states
  visibility_visible: "Visible",
  visibility_hidden: "Hidden",
  visibility_ignored: "Ignored",
  
  // Errors
  error_loading: "Error loading chart data",
  error_too_many_topics: "Please select at most 20 topics",
};
