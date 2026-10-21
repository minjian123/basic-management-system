import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.spec.ts'],
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
