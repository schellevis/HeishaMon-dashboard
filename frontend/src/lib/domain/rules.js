/** Domain facts shared with the backend (rules.json, R1): curve limits and leaf names, operating
 * mode sets, power topic pairs, S0 meters and the built-in Overview tile ids. */
import rules from '$rules';

export const curveLimits = rules.curve_limits;
export const curveEnds = rules.curve_ends;
export const curveShift = rules.curve_shift;
export const roomSensorValues = rules.room_sensor_values;
export const modeSets = rules.operating_modes;
export const s0Meters = rules.s0_meters;
export const tileIds = rules.tiles;

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/** Topic key of one curve point. `end`: cold | warm, or the raw High | Low name; `group`: outside | target. */
export function curveLeaf(zone, mode, group, end) {
  const key = String(end).toLowerCase();
  const name = rules.curve_ends[key]?.[group] ?? cap(key);
  return rules.curve_leaf
    .replace('{zone}', String(zone))
    .replace('{Mode}', cap(String(mode)))
    .replace('{Group}', cap(String(group)))
    .replace('{End}', name);
}

const leafRegex = (pattern) =>
  new RegExp(
    `^${pattern
      .replace(/[.*+?^$()|[\]\\]/g, '\\$&')
      .replace('{zone}', '(\\d)')
      .replace('{Mode}', '(Heat|Cool)')
      .replace('{Group}', '(Outside|Target)')
      .replace('{End}', '(High|Low)')}$`,
  );
const LEAF_REGEX = leafRegex(rules.curve_leaf);
const BARE_LEAF_REGEX = leafRegex(rules.curve_leaf.slice(rules.curve_leaf.lastIndexOf('/') + 1));

/** Match groups [, zone, Mode, Group, End] of a curve topic key (bare or with its prefix), else null. */
export function curveLeafMatch(key) {
  return LEAF_REGEX.exec(key) ?? BARE_LEAF_REGEX.exec(key);
}

export function hasExtra(profile) {
  const flag = profile?.has_extra;
  return flag?.value === true && !flag.unknown;
}

/** { pairs: { mode: [productionKey, consumptionKey] }, estimate }: extra/ when the profile reports it, else main/. */
export function powerPairs(profile) {
  return hasExtra(profile)
    ? { pairs: rules.power_pairs.extra, estimate: false }
    : { pairs: rules.power_pairs.main, estimate: true };
}
