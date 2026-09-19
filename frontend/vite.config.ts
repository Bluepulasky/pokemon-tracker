import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Where the Flask API listens during `npm run dev` (see `make dev`).
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8080';

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  // Flask serves the build output under /static; the dev server serves from /.
  base: command === 'build' ? '/static/' : '/',
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': API_TARGET,
      '/media': API_TARGET,
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
}));
