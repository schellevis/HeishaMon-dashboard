import { translate } from './i18n/index.js';

const HEATING_MODES = new Set([0, 2, 4, 6]);
const COOLING_MODES = new Set([1, 5, 7, 8]);
const DHW_MODES = new Set([3, 4, 5, 6, 8]);

/** Age of a timestamp, for the status bar and for stale values (§9). */
export function formatAge(ms, lang = 'en') {
  if (ms == null || Number.isNaN(ms)) return translate(lang, 'common.ageUnknown');
  if (ms < 1000) return translate(lang, 'common.justNow');
  if (ms < 60_000) return translate(lang, 'common.ageSeconds', { n: Math.floor(ms / 1000) });
  if (ms < 3_600_000) return translate(lang, 'common.ageMinutes', { n: Math.floor(ms / 60_000) });
  if (ms < 86_400_000) return translate(lang, 'common.ageHours', { n: Math.floor(ms / 3_600_000) });
  return translate(lang, 'common.ageDays', { n: Math.floor(ms / 86_400_000) });
}

export function modeLabel(value, lang = 'en') {
  if (value == null || value === -1) return translate(lang, 'common.modeUnknown');
  const key = `common.mode${value}`;
  const text = translate(lang, key);
  return text === key ? translate(lang, 'common.modeUnknown') : text;
}

function topicNumber(state, key) {
  const topic = state?.topics?.[key];
  if (!topic || topic.sentinel) return null;
  return topic.value;
}

/**
 * Current activity: defrost, DHW (valve), heating, cooling, DHW-only, or idle.
 * Mode sets follow Appendix A.4.
 */
export function activityOf(state, profile) {
  if (topicNumber(state, 'main/Defrosting_State') === 1) return 'defrost';
  if (topicNumber(state, 'main/ThreeWay_Valve_State') === 1) return 'dhw';
  if (topicNumber(state, 'main/Heatpump_State') === 0) return 'idle';
  const field = profile?.operating_mode;
  const mode = field && !field.unknown ? field.value : topicNumber(state, 'main/Operating_Mode_State');
  if (HEATING_MODES.has(mode)) return 'heating';
  if (COOLING_MODES.has(mode)) return 'cooling';
  if (DHW_MODES.has(mode)) return 'dhw';
  return 'idle';
}

export function activityLabel(activity, lang = 'en') {
  const keys = {
    heating: 'common.activityHeating',
    cooling: 'common.activityCooling',
    dhw: 'common.activityDhw',
    defrost: 'common.activityDefrost',
    idle: 'common.activityIdle',
  };
  return translate(lang, keys[activity] ?? 'common.activityIdle');
}

export function errorText(state) {
  const topic = state?.topics?.['main/Error'];
  if (!topic) return null;
  const raw = topic.raw ?? '';
  if (raw === '' || raw === '0' || topic.value === 0 || topic.value === null) return null;
  return raw;
}

export function operatingModeValue(state, profile) {
  const field = profile?.operating_mode;
  if (field && !field.unknown && field.value != null) return field.value;
  return topicNumber(state, 'main/Operating_Mode_State');
}

/**
 * How a topic value is shown. While the device is offline (§9) it is greyed
 * (`value-stale`) and the age since `last_seen` is included.
 */
export function presentTopic(topicValue, { deviceOnline = 'unknown', now = Date.now(), lang = 'en' } = {}) {
  const greyed = deviceOnline === 'offline';
  const ageMs = now - (topicValue?.last_seen ?? now);
  let text = '';
  if (!topicValue || topicValue.sentinel || topicValue.value == null) {
    text = topicValue?.raw ?? '';
  } else if (topicValue.enum_label) {
    text = topicValue.enum_label[lang] || topicValue.enum_label.en || String(topicValue.value);
  } else if (topicValue.kind === 'number' && typeof topicValue.value === 'number') {
    const rendered = topicValue.decimals == null
      ? String(topicValue.value)
      : topicValue.value.toFixed(topicValue.decimals);
    text = topicValue.unit ? `${rendered} ${topicValue.unit}` : rendered;
  } else {
    text = String(topicValue.value);
  }
  return {
    text,
    greyed,
    className: greyed ? 'value-stale' : '',
    ageMs: greyed ? ageMs : null,
    ageText: greyed ? formatAge(Math.max(0, ageMs), lang) : '',
  };
}
