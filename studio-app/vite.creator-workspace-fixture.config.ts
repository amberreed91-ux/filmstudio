import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** Fixture preview only: never imports the normal backend supervisor or targets port 8010. */
export default defineConfig({
  base: '/',
  plugins: [tailwindcss(), react()],
  build: {
    outDir: 'dist-creator-workspace-fixture',
    emptyOutDir: true,
    rollupOptions: {
      input: 'creator-workspace-fixture.html',
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5178,
    strictPort: true,
    allowedHosts: ['localhost', '127.0.0.1'],
    proxy: {
      '/api/f51/studio/projects': {
        target: 'http://127.0.0.1:8011',
        changeOrigin: true,
      },
    },
  },
})
