import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';

export default defineConfig({
  plugins: [svelte({ compilerOptions: { runes: true } }), svelteTesting()],
  cacheDir: process.env.VITE_CACHE_DIR || '/tmp/vite-heishamon',
  resolve: {
    alias: {
      $catalog: fileURLToPath(new URL('../backend/tests/fixtures/catalog_min.json', import.meta.url)),
      $rules: fileURLToPath(new URL('../backend/heishamon_dashboard/rules.json', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.js', 'src/**/*.test.js'],
  },
});
