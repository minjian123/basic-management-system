import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    // Vant 组件（按需样式）内联处理：其 `style` 依赖 .css，外部化后 Node 无法加载
    server: {
      deps: {
        inline: ['vant'],
      },
    },
    // 覆盖率门禁（阈值口径见《测试规范》「覆盖率要求」节与 04_01 详细设计 §6.2）
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: 'coverage',
      thresholds: { statements: 70, branches: 70, functions: 70, lines: 70 },
    },
  },
})
