import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [svelte()],
  base: './', // static files, servable from any path
  worker: { format: 'es' },
});
