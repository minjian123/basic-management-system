import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    // 交互用例（jsdom + Element Plus 过渡）在 CI 容器负载下会逼近缺省 5s 上限（2026-10-18 两次实测超时）
    // ⇒ 包级放宽到 20s（通过用例不受影响，仅在真挂起时晚一点失败）
    testTimeout: 20_000,
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
      // 覆盖率门槛与维度口径见 bms文档/规范/AI开发规范.md「覆盖率要求」节（唯一权威）。
      // 全包阈值不在此固化（存量缺口随阶段补齐）；验收按变更源文件门禁：
      // `vitest run --coverage --coverage.include=<变更文件> --coverage.thresholds.lines=100 ...`
    },
  },
})
