/** Power topic choice and live COP. The source follows the installation profile (`has_extra`),
 * never the data seen: extra/ when the heat pump reports the extra block, else the coarse main/ pair.
 * Mirrors backend `derived.power_topics`; the pairs come from rules.json. */

import { hasExtra, powerPairs } from './rules.js';

export { hasExtra, powerPairs };
export const POWER_MODES = Object.keys(powerPairs(null).pairs);

function watts(tv) {
  return tv && !tv.sentinel && typeof tv.value === 'number' ? tv.value : null;
}

/** Topic-value-shaped heat COP (production / consumption), or null unless both are readable and consumption > 0. */
export function liveCop(values, profile) {
  const [prodKey, consKey] = powerPairs(profile).pairs.heat;
  const production = values?.[prodKey];
  const consumption = values?.[consKey];
  const prod = watts(production);
  const cons = watts(consumption);
  if (prod === null || cons === null || cons <= 0) return null;
  const value = prod / cons;
  return {
    value,
    raw: value.toFixed(2),
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
