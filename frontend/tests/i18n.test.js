import { describe, expect, it } from 'vitest';
import { languages, messages, translate } from '../src/lib/i18n/index.js';
import { initialLanguage } from '../src/lib/i18n/index.js';

const enModules = import.meta.glob('../src/lib/i18n/*.en.js', { eager: true, import: 'default' });
const nlModules = import.meta.glob('../src/lib/i18n/*.nl.js', { eager: true, import: 'default' });

function moduleName(path, lang) {
  return path.replace(/^.*\//, '').replace(new RegExp(`\\.${lang}\\.js$`), '');
}

describe('i18n key parity', () => {
  it('pairs every *.en.js module with a *.nl.js module and the same keys', () => {
    const enNames = Object.keys(enModules).map((path) => moduleName(path, 'en')).sort();
    const nlNames = Object.keys(nlModules).map((path) => moduleName(path, 'nl')).sort();
    expect(enNames.length).toBeGreaterThan(0);
    expect(nlNames).toEqual(enNames);

    for (const name of enNames) {
      const enPath = Object.keys(enModules).find((path) => moduleName(path, 'en') === name);
      const nlPath = Object.keys(nlModules).find((path) => moduleName(path, 'nl') === name);
      const enKeys = Object.keys(enModules[enPath]).sort();
      const nlKeys = Object.keys(nlModules[nlPath]).sort();
      expect(nlKeys, name).toEqual(enKeys);
      for (const key of enKeys) {
        expect(typeof enModules[enPath][key]).toBe('string');
        expect(typeof nlModules[nlPath][key]).toBe('string');
        expect(enModules[enPath][key].length).toBeGreaterThan(0);
        expect(nlModules[nlPath][key].length).toBeGreaterThan(0);
      }
    }
  });

  it('merges module tables under <module>.<key> with an English fallback', () => {
    expect(languages).toEqual(['en', 'nl']);
    expect(messages.en['common.apply']).toBe('Apply');
    expect(messages.nl['common.apply']).toBe('Toepassen');
    expect(translate('nl', 'common.apply')).toBe('Toepassen');
    expect(translate('fr', 'common.apply')).toBe('Apply');
    expect(translate('nl', 'missing.key')).toBe('missing.key');
    expect(translate('en', 'common.ageMinutes', { n: 2 })).toBe('2 min');
  });
});

describe('language selection', () => {
  const memory = (initial) => {
    const data = { ...initial };
    return {
      getItem: (key) => (key in data ? data[key] : null),
      setItem: (key, value) => {
        data[key] = value;
      },
      data,
    };
  };

  it('prefers the stored language, then a Dutch browser, then English', () => {
    expect(initialLanguage(memory({ 'heishamon.language': 'en' }), { language: 'nl-NL' })).toBe('en');
    expect(initialLanguage(memory({ 'heishamon.language': 'nl' }), { language: 'en-US' })).toBe('nl');
    expect(initialLanguage(memory({}), { language: 'nl-BE' })).toBe('nl');
    expect(initialLanguage(memory({}), { languages: ['nl'] })).toBe('nl');
    expect(initialLanguage(memory({ 'heishamon.language': 'de' }), { language: 'fr-FR' })).toBe('en');
    expect(initialLanguage(memory({}), { language: 'en-US' })).toBe('en');
    expect(initialLanguage(memory({}), {})).toBe('en');
  });
});
