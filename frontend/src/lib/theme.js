/** Day/night theme: browser-local like the language (spec 2026-10-14 §3), never a server pref. */
import { derived, writable } from 'svelte/store';

export const THEME_KEY = 'heishamon.theme';
const VALID = new Set(['day', 'night']);

export const themeChoice = writable(null);
const systemLight = writable(false);
export const resolvedTheme = derived([themeChoice, systemLight], ([choice, light]) => choice ?? (light ? 'day' : 'night'));

let store = null;

export function setTheme(choice) {
  const next = VALID.has(choice) ? choice : null;
  themeChoice.set(next);
  if (next) store?.setItem?.(THEME_KEY, next);
  else store?.removeItem?.(THEME_KEY);
}

export function initTheme({
  storage = globalThis.localStorage,
  media = globalThis.matchMedia?.('(prefers-color-scheme: light)'),
  root = globalThis.document?.documentElement,
} = {}) {
  store = storage;
  const saved = storage?.getItem?.(THEME_KEY);
  themeChoice.set(VALID.has(saved) ? saved : null);
  systemLight.set(Boolean(media?.matches));
  const onMedia = (event) => systemLight.set(Boolean(event.matches));
  media?.addEventListener?.('change', onMedia);
  const unsub = resolvedTheme.subscribe((theme) => {
    if (root) root.dataset.theme = theme;
  });
  return () => {
    unsub();
    media?.removeEventListener?.('change', onMedia);
  };
}

/** Current value of a CSS custom property (charts need concrete colours). */
export function cssVar(name, root = globalThis.document?.documentElement) {
  if (!root || !globalThis.getComputedStyle) return '';
  return getComputedStyle(root).getPropertyValue(name).trim();
}
