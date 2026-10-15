import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxy = {
  '/api': {
    target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8250',
    changeOrigin: true,
  },
  '/preflight': {
    target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8250',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5250, strictPort: true, proxy: apiProxy },
  preview: { host: '127.0.0.1', port: 5250, strictPort: true, proxy: apiProxy },
})
