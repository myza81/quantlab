/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/health': 'http://localhost:8000',
      '/market-data': 'http://localhost:8000',
      '/datasets': 'http://localhost:8000',
      '/strategy-runs': 'http://localhost:8000',
      '/tools': 'http://localhost:8000',
      '/drafts': 'http://localhost:8000',
      '/semantics': 'http://localhost:8000',
      '/backtests': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/provider-credentials': 'http://localhost:8000',
      '/catalog': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
