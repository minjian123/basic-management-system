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
    // 覆盖率门禁（骨架期口径：统计被用例导入的文件；全量 src/** 随阶段四组件库扩面）
    // 阈值口径见《测试规范》「覆盖率要求」节与 04_01 详细设计 §6.2
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: 'coverage',
      thresholds: { statements: 70, branches: 70, functions: 70, lines: 70 },
    },
  },
})
