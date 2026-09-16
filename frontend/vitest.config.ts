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
      // 纯再导出的 barrel 文件（无逻辑）不计入统计，避免 0% 拉低聚合口径
      exclude: ['src/components/base/index.ts', 'src/components/base/*/index.ts'],
      thresholds: { statements: 70, branches: 70, functions: 70, lines: 70 },
    },
  },
})
