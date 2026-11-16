/** 24×24 stroke icons for the nav, keyed by screen id. */
export const ICONS = {
  overview: 'M3 12h4l3-7 4 14 3-7h4',
  charts: 'M4 19V5M4 19h16M8 15l4-5 3 3 5-6',
  energy: 'M13 3 5 13h6l-1 8 8-10h-6z',
  curve: 'M4 7h4l8 10h4M8 5.2a1.8 1.8 0 1 0 0 3.6 1.8 1.8 0 1 0 0-3.6M16 15.2a1.8 1.8 0 1 0 0 3.6 1.8 1.8 0 1 0 0-3.6',
  settings: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 6a2 2 0 1 0 4 0 2 2 0 1 0-4 0M8 12a2 2 0 1 0 4 0 2 2 0 1 0-4 0M16 18a2 2 0 1 0 4 0 2 2 0 1 0-4 0',
  topics: 'M5 6h14M5 12h14M5 18h9',
  log: 'M6 4h9l3 3v13H6zM9 11h6M9 15h6',
  system: 'M4 5h16v10H4zM9 19h6M12 15v4',
};
const FALLBACK = 'M12 9a3 3 0 1 0 0 6 3 3 0 1 0 0-6';

export function iconFor(id) {
  return ICONS[id] ?? FALLBACK;
}
