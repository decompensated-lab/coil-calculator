import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [svelte()],
  base: './', // static files, servable from any path
  worker: { format: 'es' },
  // rust/target holds thousands of build files; the app only reads the copied .wasm
  server: { watch: { ignored: ['**/rust/**'] } },
});
