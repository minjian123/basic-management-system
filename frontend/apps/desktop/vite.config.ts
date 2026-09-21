import { fileURLToPath, URL } from 'node:url'

import { federation } from '@module-federation/vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vite'

import { loadSharedDependencies } from '../../scripts/shared-deps.mjs'

/**
 * Module Federation 共享依赖（**单例 + 版本要求**）：共享面与 `requiredVersion` 取自
 * **单一来源** `frontend/shared-dependencies.json`（宿主与模块两侧同源，不得各写一份）；
 * 宿主为**提供方**——不设 `import: false`（须打包并提供实例），不设 `strictVersion`（拒绝权在消费方）。
 *
 * 共享面之外的 `element-plus` 与平台基座包（`@bms/core` / `@bms/ui-ep`）登记在单一来源的
 * `notShared`（含理由与实测数据），由白名单护栏与体积阈值守住（见任务 02_02 详细设计 §3.1 / §3.7）。
 */
const { shared: SHARED_DEPENDENCIES } = loadSharedDependencies({ role: 'host' })

// BMS PC 管理端：固定开发端口 5173；/api 与 /healthz 代理 backend，/info 重写至 backend 根（连通验证）
// Module Federation：仅作**纯 host**（`name` + `shared`）——远端地址来自模块清单，运行期经
// `registerRemotes` + `loadRemote` 注册与加载，改清单不必重构建（见任务 02_01 详细设计 §3.3）。
export default defineConfig({
  plugins: [
    vue(),
    Components({ resolvers: [ElementPlusResolver()] }),
    federation({ name: 'bms-desktop', shared: SHARED_DEPENDENCIES }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 基座（源码直出包）：与包 exports 设定一致
      '@bms/core': fileURLToPath(new URL('../../packages/core/src/index.ts', import.meta.url)),
      '@bms/vue': fileURLToPath(new URL('../../packages/vue/src/index.ts', import.meta.url)),
      '@bms/ui-ep': fileURLToPath(new URL('../../packages/ui-ep/src/index.ts', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id: string): string | undefined => {
          if (id.includes('node_modules/element-plus') || id.includes('node_modules/@element-plus')) {
            return 'vendor-element-plus'
          }
          // 图表库独立分包（仅动态 import 时成为异步块，不进首屏）
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) {
            return 'vendor-echarts'
          }
          // 网格库独立分包（仅动态 import 时成为异步块，不进首屏）
          if (id.includes('node_modules/gridstack')) {
            return 'vendor-gridstack'
          }
          // 自由画布库独立分包（仅动态 import 时成为异步块，不进首屏）
          if (id.includes('node_modules/@vue-flow')) {
            return 'vendor-vue-flow'
          }
          // Markdown 渲染库独立分包（仅 AI 面板动态 import 时成为异步块，不进首屏）
          if (id.includes('node_modules/marked')) {
            return 'vendor-marked'
          }
          // 图片裁剪库独立分包（仅裁剪弹窗动态 import 时成为异步块，不进首屏）
          if (id.includes('node_modules/cropperjs')) {
            return 'vendor-cropperjs'
          }
          if (id.includes('/packages/')) {
            return 'bms-base'
          }
          return undefined
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/healthz': { target: 'http://localhost:8000', changeOrigin: true },
      '/info': { target: 'http://localhost:8000', changeOrigin: true, rewrite: () => '/' },
    },
  },
})
