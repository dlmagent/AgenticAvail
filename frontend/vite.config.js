import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/chat': backendTarget,
      '/health': backendTarget,
      '/capabilities': backendTarget,
      '/invoke': backendTarget,
    },
  },
})
