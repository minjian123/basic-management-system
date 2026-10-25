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
      '@bms/ui_ep': fileURLToPath(new URL('../../packages/ui_ep/src/index.ts', import.meta.url)),
      '@bms/api_types': fileURLToPath(new URL('../../packages/api_types/src/index.ts', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    // 并发上限（2026-10-22 实测）：桌面包 100 个测试文件，默认按文件各 fork 一个 worker ⇒ 本机
    // 100 worker 同时 transform，重型文件（`router-index` / `menu-sections`）的 import 被拖慢约
    // 10 倍，稳定撞 15s 超时。限到核数一半后 **868 passed + 覆盖率 100%**（4 worker 73s /
    // 8 worker 51s），零超时；CI 按 job 容器核数自适应，不必另设。
    maxWorkers: '50%',
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
