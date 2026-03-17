import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    include: ['recharts'],
  },
  build: {
    rollupOptions: {
      output: {
        hoistTransitiveImports: false,
        manualChunks: {
          'vendor-react':  ['react', 'react-dom', 'react-router-dom'],
          'vendor-charts': ['recharts', 'd3-shape', 'd3-scale', 'd3-selection',
                            'd3-interpolate', 'd3-transition', 'd3-zoom',
                            'd3-color', 'd3-path', 'd3-array'],
        },
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
