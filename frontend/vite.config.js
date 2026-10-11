import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  cacheDir: process.env.VITE_CACHE_DIR || '/tmp/vite-heishamon',
  resolve: {
    alias: {
      $catalog: fileURLToPath(new URL('../backend/heishamon_dashboard/catalog.json', import.meta.url)),
    },
  },
});
