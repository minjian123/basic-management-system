import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [ElementPlusResolver()] })],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@bms/core': fileURLToPath(new URL('../../packages/core/src/index.ts', import.meta.url)),
      '@bms/vue': fileURLToPath(new URL('../../packages/vue/src/index.ts', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    server: {
      deps: {
        inline: ['element-plus'],
      },
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: 'coverage',
      thresholds: { statements: 70, branches: 70, functions: 70, lines: 70 },
    },
  },
})
