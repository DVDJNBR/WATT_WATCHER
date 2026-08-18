import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Force recharts through its CJS lib/ instead of ESM es6/.
    // esbuild pre-bundles CJS and resolves the 8 recharts circular deps
    // (Area↔areaSelectors, Bar↔barSelectors, Line↔lineSelectors, …)
    // that otherwise cause TDZ crashes in the Rollup production bundle.
    alias: {
      recharts: path.resolve('./node_modules/recharts/lib/index.js'),
    },
  },
  server: {
    proxy: {
      // Proxy /api to the local FastAPI dev server (uvicorn api.main:app --port 8000)
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
  },
})
