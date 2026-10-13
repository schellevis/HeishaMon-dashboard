// One import line per feature; delete a feature's folder and its line to remove it.
import overview from '../features/overview/index.js';
import charts from '../features/charts/index.js';
import energy from '../features/energy/index.js';
import curve from '../features/curve/index.js';
import settings from '../features/settings/index.js';
import topics from '../features/topics/index.js';
import log from '../features/log/index.js';
import system from '../features/system/index.js';

const registry = [overview, charts, energy, curve, settings, topics, log, system].sort(
  (a, b) => a.order - b.order,
);

export const ROUTES = registry.map((feature) => feature.id);

export default registry;
