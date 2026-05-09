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
    },
  },
})
