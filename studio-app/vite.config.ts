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
  server: {
    port: 5000,
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/projects': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/outputs': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
