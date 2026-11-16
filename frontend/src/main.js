import { mount } from 'svelte';
import '@fontsource/instrument-sans/400.css';
import '@fontsource/instrument-sans/500.css';
import '@fontsource/instrument-sans/600.css';
import '@fontsource-variable/martian-mono/wdth.css'; // the file chosen in Step 1
import 'uplot/dist/uPlot.min.css';
import './app.css';
import { initTheme } from './lib/theme.js';
import App from './app/App.svelte';

initTheme();
const app = mount(App, { target: document.getElementById('app') });

export default app;
