export default {
  // Tile labels
  outsideTemp: 'Outside temperature',
  mainOutletTemp: 'Outlet temperature',
  mainInletTemp: 'Inlet temperature',
  deltaTemp: 'ΔT',
  compressorFreq: 'Compressor frequency',
  heatPowerConsumption: 'Heat power consumption',
  heatPowerProduction: 'Heat power production',
  cop: 'COP',
  threeWayValve: 'Three-way valve',
  defrostingState: 'Defrost',
  dhwTemp: 'DHW temperature',
  bufferTemp: 'Buffer temperature',
  solarTemp: 'Solar temperature',
  coolPowerProduction: 'Cooling power',

  // Tile management
  pinTile: 'Pin',
  unpinTile: 'Unpin',
  reorderTiles: 'Reorder tiles',
  manageTiles: 'Manage tiles',
  addTile: 'Add tile',
  defaultTiles: 'Default tiles',
  customTiles: 'Custom tiles',
  noPinnedTiles: 'No pinned tiles yet',
  resetTiles: 'Reset to defaults',

  // Quick controls
  heatPump: 'Heat pump',
  forceDhwNeedsMode: 'Only in an operating mode with DHW.',
  quickControls: 'Quick controls',
  heatPumpOn: 'Heat pump on',
  heatPumpOff: 'Heat pump off',
  operatingMode: 'Operating mode',
  quietMode: 'Quiet mode',
  powerfulMode: 'Powerful mode',
  forceDhw: 'Force DHW',
  dhwSetpoint: 'DHW setpoint',

  // Zone request controls (mode-adaptive)
  heatRequest: 'Heat request',
  coolRequest: 'Cool request',
  requestShift: 'shift',
  requestSetpoint: 'setpoint',
  coupledNote: 'Direct mode with a room thermostat or thermistor: the heat pump keeps this setpoint in the curve\'s cold-end target ({key}), not in the request temperature. Apply changes that curve value.',
  coupledLink: 'Open the curve',

  // Unit labels
  unitCelsius: '°C',
  unitPercent: '%',
  unitWatt: 'W',
  unitKilowatt: 'kW',
  unitHertz: 'Hz',

  // Mode labels for controls
  modeCurve: 'Curve',
  modeDirect: 'Direct',

  // EEPROM warning (3 per 60 minutes)
  eepromWarning: 'Changing settings frequently can wear the heat pump memory. Please wait at least 20 minutes between changes.',
  eepromWarningTitle: 'EEPROM wear warning',

  // Sparkline
  sparkline24h: '24 h',

  // Zone labels
  zone1: 'Zone 1',
  zone2: 'Zone 2',

  // Value labels
  on: 'On',
  off: 'Off',
};
