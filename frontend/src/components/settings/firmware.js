/** Appendix A.1 firmware comparison for the settings gates (spec §6). */

const ASSUMED = [3, 2, 3];

export function parseFirmware(version) {
  if (version == null || String(version).trim() === '') return { tuple: ASSUMED, assumed: true };
  let text = String(version).trim();
  if (text.startsWith('v')) text = text.slice(1);
  const match = /^(\d+)\.(\d+)(?:\.(\d+))?/.exec(text);
  if (!match) return { tuple: ASSUMED, assumed: true };
  const major = Number(match[1]);
  const minor = match[2];
  const patch = match[3];
  if (patch == null) {
    if (minor.length === 2 && minor[0] !== '0') {
      return { tuple: [major, Number(minor[0]), Number(minor[1])], assumed: false };
    }
    return { tuple: [major, Number(minor), 0], assumed: false };
  }
  return { tuple: [major, Number(minor), Number(patch)], assumed: false };
}

/** Version used for gating. Unknown or stale firmware counts as 3.2.3 (spec §4.3, §6). */
export function activeFirmware(profile) {
  if (!profile || profile.firmware_assumed) return ASSUMED;
  const node = profile.firmware;
  if (!node || node.unknown || node.stale) return ASSUMED;
  const parsed = parseFirmware(node.value);
  return parsed.assumed ? ASSUMED : parsed.tuple;
}

export function cmpVersion(left, right) {
  for (let i = 0; i < 3; i += 1) {
    if (left[i] !== right[i]) return left[i] < right[i] ? -1 : 1;
  }
  return 0;
}
