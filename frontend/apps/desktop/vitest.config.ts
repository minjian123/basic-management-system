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
      '@bms/ui-ep': fileURLToPath(new URL('../../packages/ui-ep/src/index.ts', import.meta.url)),
      '@bms/api-types': fileURLToPath(new URL('../../packages/api-types/src/index.ts', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    // 单例超时（缺省 5s 在 CI 机器上偏紧）：宿主用例普遍挂**真实** `el-table` / 懒加载路由视图，
    // CI 并发下重型文件（`user-record-tab` / `account-lock-view` / `*-view` / 路由族）可达本地的数倍，
    // 实测多次撞 5s（2026-10-13：account-lock-view 2 例、user-record-tab 1 例）⇒ 统一放宽到 15s，
    // 避免逐个文件打补丁；真实挂死仍会在 15s 内暴露。
    testTimeout: 15000,
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
      thresholds: { statements: 100, branches: 100, functions: 100, lines: 100 },
    },
  },
})
