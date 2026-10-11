// Merges the per-module string tables `<module>.en.js` / `<module>.nl.js` (default export:
// a flat object of key -> string). Keys are namespaced as `<module>.<key>`.
const tables = {
  en: import.meta.glob('./*.en.js', { eager: true, import: 'default' }),
  nl: import.meta.glob('./*.nl.js', { eager: true, import: 'default' }),
};

function merge(lang) {
  const out = {};
  for (const [path, table] of Object.entries(tables[lang])) {
    const module = path.replace(/^\.\//, '').replace(new RegExp(`\\.${lang}\\.js$`), '');
    for (const [key, value] of Object.entries(table)) out[`${module}.${key}`] = value;
  }
  return out;
}

export const messages = { en: merge('en'), nl: merge('nl') };
export const languages = Object.keys(messages);

export const LANGUAGE_KEY = 'heishamon.language';

export function translate(lang, key, params = {}) {
  const text = messages[lang]?.[key] ?? messages.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

/** Stored choice, otherwise a Dutch browser language, otherwise English. */
export function initialLanguage(storage = globalThis.localStorage, nav = globalThis.navigator) {
  const saved = storage?.getItem?.(LANGUAGE_KEY);
  if (saved === 'en' || saved === 'nl') return saved;
  const list = [nav?.language, ...(nav?.languages ?? [])].filter(Boolean);
  if (list.some((tag) => String(tag).toLowerCase().startsWith('nl'))) return 'nl';
  return 'en';
}
