import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['tests/vitest.setup.ts'],
    include: ['tests/{unit,integration}/**/*.{test,spec}.ts'],
    exclude: ['tests/e2e/**']
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})