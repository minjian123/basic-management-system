import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    // 全量测试守卫：开发期间无过滤全跑会被拒绝（实现唯一在 engkit，口径见《测试规范》）
    globalSetup: ['../../../scripts/testing/vitest_guard.mjs'],
    environment: 'node',
    include: ['tests/**/*.spec.ts'],
  },
})
