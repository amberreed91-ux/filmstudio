import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { backendSupervisorPlugin } from './backendSupervisor'

export default defineConfig({
  base: '/',
  plugins: [
    backendSupervisorPlugin(),
    tailwindcss(),
    react(),
  ],
  build: {
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/three') || id.includes('node_modules/@react-three')) {
            return 'vendor-three';
          }
          if (id.includes('node_modules/framer-motion') || id.includes('node_modules/lucide-react') || id.includes('node_modules/clsx')) {
            return 'vendor-ui';
          }
          if (id.includes('node_modules/recharts')) {
            return 'vendor-charts';
          }
          if (id.includes('node_modules/@tanstack/react-query')) {
            return 'vendor-query';
          }
        },
      },
    },
  },
  server: {
    port: 5001,
    host: '127.0.0.1',
    allowedHosts: ['localhost', '127.0.0.1'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
      '/projects': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
      '/outputs': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
      '/previs-assets': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
    },
  },
})
