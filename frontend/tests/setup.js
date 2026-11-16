import { vi } from 'vitest';

// jsdom has neither canvas nor ResizeObserver. Chart components get a no-op uPlot in every test file;
// a file that mocks 'uplot' itself (charts.test.js) overrides this. Real charts are checked in Playwright.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('uplot', () => {
  class FakeUplot {
    constructor(opts, data, el) {
      this.opts = opts;
      this.data = data;
      this.el = el;
      this.cursor = { idx: null };
      this.destroyed = false;
      FakeUplot.instances.push(this);
    }
    setData(data) { this.data = data; }
    setSize() {}
    redraw() {}
    valToPos() { return 0; }
    destroy() { this.destroyed = true; }
  }
  FakeUplot.instances = [];
  FakeUplot.paths = { stepped: () => () => null };
  return { default: FakeUplot };
});
