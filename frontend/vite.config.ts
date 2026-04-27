import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './vitest.setup.ts',
    include: ['src/**/*.spec.ts'],
    exclude: ['tests/e2e/**'],
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/3d-force-graph/')) {
            return 'force-graph-vendor'
          }
          if (id.includes('/node_modules/three/')) {
            return 'three-vendor'
          }
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      // Playwright writes artifacts during parallel runs; ignoring them prevents
      // Vite from triggering full-page reloads mid-test.
      ignored: [
        '**/test-results/**',
        '**/playwright-report/**',
        '**/.playwright/**',
      ],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
