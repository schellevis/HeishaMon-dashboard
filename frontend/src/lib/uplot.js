/** uPlot wrapper for HeishaMon dashboard charts.
 * 
 * uPlot is a lightweight, high-performance charting library.
 * This module provides a thin wrapper to simplify chart creation and updates.
 * uPlot is imported dynamically to avoid breaking tests that don't need it.
 */

import { axisFormatter } from './time.js';
import { cssVar } from './theme.js';

/** uPlot series: series[0] describes the x axis; enum bands and `stepped` series draw as steps. */
export function buildSeries(series = [], Uplot = null) {
  return [{}, ...series.map((s) => {
    const { enumBand, stepped, ...rest } = s;
    if ((enumBand || stepped) && Uplot?.paths?.stepped) rest.paths = Uplot.paths.stepped({ align: 1 });
    return rest;
  })];
}

/** Axes coloured from the current theme; explicit settings win. */
export function themedAxes(axes = []) {
  const ink = cssVar('--ink-3') || undefined;
  const line = cssVar('--line') || undefined;
  return axes.map((axis) => ({
    stroke: ink,
    grid: { stroke: line, width: 1 },
    ticks: { stroke: line, width: 1 },
    font: '10px "Martian Mono Variable", monospace',
    ...axis,
  }));
}

// Dynamic import of uplot to avoid module-level side effects
let uplotPromise = null;

/** Get uplot module dynamically */
async function getUplot() {
  if (!uplotPromise) {
    uplotPromise = import('uplot');
  }
  return uplotPromise;
}

/** Default chart options for HeishaMon */
export const DEFAULT_OPTIONS = {
  width: 800,
  height: 400,
  padding: [20, 40, 20, 60],
  cursor: {
    x: false,
    y: false,
  },
  scales: {
    x: {
      time: true,
    },
    y: {
      auto: true,
    },
  },
  series: [],
  legend: {
    show: true,
    live: false,
  },
};

/** Color scheme for chart series */
export const COLORS = ['#f0a04b', '#4fa3e0', '#6cc59a', '#e5533d', '#8fb8c9', '#b48ce0', '#e8c25a', '#93a3b0', '#d07fb0', '#5fc4c0'];

/** Enum value to color mapping for band rendering */
export const ENUM_COLORS = { 0: '#64737f', 1: '#4fa3e0', 2: '#f0a04b', 3: '#6cc59a', 4: '#e5533d', 5: '#b48ce0', 6: '#8fb8c9', 7: '#d07fb0', 8: '#93a3b0', 9: '#e8c25a', 10: '#5fc4c0' };

/** Create a chart instance
 * @param {HTMLElement} element - DOM element to render the chart in
 * @param {Object} options - uPlot options
 * @returns {Promise<Object>} Promise resolving to chart instance with update method
 */
export async function createChart(element, options = {}) {
  const uplot = await getUplot();
  const Uplot = uplot.default || uplot;
  
  const mergedOptions = {
    ...DEFAULT_OPTIONS,
    ...options,
  };

  const series = buildSeries(mergedOptions.series || [], Uplot);
  const chart = new Uplot({ ...mergedOptions, series }, mergedOptions.data || [], element);

  return {
    chart,
    element,
    
    /** Update chart data
     * @param {Array} data - Array of series data arrays
     * @param {boolean} animate - Whether to animate the update
     */
    update(data, animate = false) {
      chart.setData(data, animate);
    },

    /** Resize without recreating */
    setSize(width, height) {
      if (chart.setSize) chart.setSize({ width, height });
    },
    
    /** Destroy the chart and clean up */
    destroy() {
      chart.destroy();
    },
    
    /** Get the chart instance */
    getInstance() {
      return chart;
    },
  };
}

/** Format timestamp for chart display
 * @param {number} ts - Unix timestamp in milliseconds
 * @returns {string} Formatted date/time string
 */
export function formatTimestamp(ts, lang = 'en') {
  const date = new Date(ts);
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/** Format date for chart display
 * @param {number} ts - Unix timestamp in milliseconds
 * @returns {string} Formatted date string
 */
export function formatDate(ts, lang = 'en') {
  const date = new Date(ts);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Place one series on the shared x axis. Missing timestamps repeat the series' last value (LOCF)
 * only while the series has a value there: never before its first point, after a null
 * (zero-coverage) point, or across one of its breaks. */
function alignSeries(points, axisMs, breaks, locf) {
  const sorted = [...points].sort((a, b) => a[0] - b[0]);
  let i = 0;
  let last = null;
  return axisMs.map((ms) => {
    while (i < sorted.length && sorted[i][0] <= ms) last = sorted[i++];
    if (!last) return null;
    if (last[0] === ms) return last[1];
    if (!locf || last[1] === null) return null;
    // a break overlapping (last point, ms] means the value was not held
    if (breaks.some(([start, end]) => start <= ms && end > last[0])) return null;
    return last[1];
  });
}

/** Convert History API series to uPlot data
 * @param {Object} history - History response from API
 * @param {Object} catalog - Optional catalog for topic info
 * @returns {Object} uPlot options ready for chart creation
 */
export function historyToUplot(history, catalog = null, { lang = 'en', timeZone } = {}) {
  const { series } = history;

  const uplotSeries = [];
  const allBreaks = [];

  // Shared x axis: union of all series timestamps (History timestamps are unix ms; uPlot wants s)
  const tsSet = new Set();
  for (const sd of Object.values(series)) {
    for (const point of sd.points) tsSet.add(point[0]);
  }
  const msAxis = [...tsSet].sort((x, y) => x - y);
  const timeData = msAxis.map((ms) => ms / 1000);
  const uplotData = msAxis.length || Object.keys(series).length ? [timeData] : [];

  // Raw points are change-only (LOCF); rollup buckets are real samples and stay as they are.
  const locf = !history.resolution || history.resolution === 'raw';
  let colorIndex = 0;

  for (const [key, seriesData] of Object.entries(series)) {
    const catalogTopic = catalog ? catalog.topics.find(t => t.key === key) : null;
    const isEnum = seriesData.kind === 'enum' || (catalogTopic && catalogTopic.kind === 'enum');

    const name = catalogTopic ? (catalogTopic.label?.[lang] || catalogTopic.label?.en || key) : key;
    const label = catalogTopic?.unit && !isEnum ? `${name} (${catalogTopic.unit})` : name;
    const color = COLORS[colorIndex % COLORS.length];
    colorIndex++;

    const pts = [];
    for (const point of seriesData.points) {
      let v = point[1];
      if (seriesData.kind === 'text') v = null; // text cannot be plotted numerically
      else if (point.length > 2 && point[2] === 0) v = null; // zero-coverage rollup bucket
      pts.push([point[0], v === undefined ? null : v]);
    }
    uplotData.push(alignSeries(pts, msAxis, seriesData.breaks || [], locf));
    for (const br of seriesData.breaks || []) allBreaks.push(br);

    const seriesOpts = { label, width: 2, spanGaps: false };
    if (isEnum) {
      seriesOpts.enumBand = true;
      seriesOpts.fill = color;
      seriesOpts.stroke = null;
    } else {
      seriesOpts.stroke = color;
      seriesOpts.fill = null;
    }
    uplotSeries.push(seriesOpts);
  }

  const finalData = insertBreaks(uplotData, allBreaks);

  // Add the time scale configuration
  const scales = {
    x: {
      time: true,
    },
    y: {
      auto: true,
    },
  };
  
  return {
    series: uplotSeries,
    data: finalData,
    scales,
    width: null, // Will be set by container
    height: null,
    legend: {
      show: true,
      live: false,
    },
    cursor: {
      x: false,
      y: false,
    },
    axes: timeAxes(lang, timeZone),
    padding: [12, 12, 0, 4],
  };
}

/**
 * Axes with locale-aware, 24-hour (nl) time labels in the browser's (or a given) time zone.
 * uPlot's built-in formatter uses 12-hour am/pm templates.
 */
export function timeAxes(lang = 'en', timeZone) {
  const fmt = axisFormatter(lang, { timeZone });
  const HOUR = 3600;
  const DAY = 24 * HOUR;
  return [
    {
      space: 70,
      values: (u, splits, axisIdx, foundSpace, foundIncr) => splits.map((sec) => {
        if (sec == null) return '';
        const date = new Date(sec * 1000);
        if (foundIncr < DAY) {
          const time = fmt.time.format(date);
          return time === '00:00' ? fmt.day.format(date) : time;
        }
        if (foundIncr < 28 * DAY) return fmt.day.format(date);
        if (foundIncr < 365 * DAY) return fmt.month.format(date);
        return fmt.year.format(date);
      }),
    },
    { size: 50 },
  ];
}

/** Get breaks as gaps in the data
 * @param {Array} breaks - Array of [start_ts, end_ts] outage intervals
 * @returns {Function} Function to check if a timestamp is in a break
 */
export function getBreakChecker(breaks = []) {
  return (ts) => {
    if (!breaks || breaks.length === 0) return false;
    
    for (const [start, end] of breaks) {
      if (ts >= start && ts <= end) {
        return true;
      }
    }
    return false;
  };
}

/** Insert null points at break starts so lines are interrupted there.
 * @param {Array} data - uPlot data (data[0] = x in seconds)
 * @param {Array} breaks - [start_ms, end_ms] outage intervals (History units)
 * @returns {Array} New data with a null row (all series) at each break start
 */
export function insertBreaks(data, breaks = []) {
  if (!breaks || breaks.length === 0 || data.length === 0) return data;

  const xs = data[0];
  const rows = xs.map((x, i) => ({ x, vals: data.slice(1).map((col) => col[i]) }));
  const have = new Set(xs);
  const blank = data.length - 1;
  const starts = [...new Set(breaks.map(([start]) => start / 1000))].sort((a, b) => a - b);
  for (let t of starts) {
    // keep real points: nudge off an existing timestamp (1 ms, stays before the next point)
    if (have.has(t)) t += 0.001;
    if (have.has(t)) continue;
    have.add(t);
    rows.push({ x: t, vals: new Array(blank).fill(null) });
  }
  rows.sort((a, b) => a.x - b.x);
  return [rows.map((r) => r.x), ...data.slice(1).map((_, c) => rows.map((r) => r.vals[c]))];
}

export default {
  createChart,
  formatTimestamp,
  formatDate,
  historyToUplot,
  getBreakChecker,
  insertBreaks,
  DEFAULT_OPTIONS,
  COLORS,
  ENUM_COLORS,
};
