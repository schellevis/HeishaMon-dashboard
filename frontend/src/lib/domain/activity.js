/** What the heat pump is doing, from the defrost flag, valve, on/off state and operating mode. */
import { modeSets } from './rules.js';

const HEATING = new Set(modeSets.heating);
const COOLING = new Set(modeSets.cooling);
const DHW = new Set(modeSets.dhw);
const on = (v) => typeof v === 'number' && v >= 0.5;
const known = (v) => typeof v === 'number' && Number.isFinite(v);

function fromMode(mode) {
  const m = known(mode) ? Math.round(mode) : null;
  if (HEATING.has(m)) return 'heating';
  if (COOLING.has(m)) return 'cooling';
  if (DHW.has(m)) return 'dhw';
  return null;
}

/** Strict: only claim a lower-priority activity when every higher-priority input is known (spec R3.4). */
function strictActivity({ defrost, valve, heatpump, mode }) {
  if (!known(defrost)) return 'unknown';
  if (on(defrost)) return 'defrost';
  if (!known(valve)) return 'unknown';
  if (on(valve)) return 'dhw';
  if (!known(heatpump)) return 'unknown';
  if (heatpump < 0.5) return 'idle';
  return fromMode(mode) ?? 'unknown';
}

export function activityFrom({ defrost = null, valve = null, heatpump = null, mode = null } = {}, { strict = false } = {}) {
  if (strict) return strictActivity({ defrost, valve, heatpump, mode });
  if (on(defrost)) return 'defrost';
  if (on(valve)) return 'dhw';
  if (typeof heatpump === 'number' && heatpump < 0.5) return 'idle';
  return fromMode(mode) ?? 'idle';
}
