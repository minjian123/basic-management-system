import { federation } from '@module-federation/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

/** 模块名（= 模块清单 `name` = MF 容器名；见任务 02_01 详细设计 §3.3 远端命名约定）。 */
const MODULE_NAME = 'demo'

/** 远端容器入口文件名（契约常量 `MODULE_REMOTE_ENTRY_FILE` 同值，构建期须一致）。 */
const REMOTE_ENTRY_FILE = 'remoteEntry.js'

/** 暴露键（契约常量 `MODULE_EXPOSE_KEY` 同值；模块定义默认导出）。 */
const EXPOSE_KEY = './module'

/** 固定预览端口（演示清单指向 `http://localhost:5002/remoteEntry.js`）。 */
const PORT = 5002

/**
 * Module Federation 共享依赖（**单例**）：与宿主 `frontend/apps/desktop/vite.config.ts`
 * 声明须保持一致（版本来源单一化与版本偏斜检查归 `02_02`）。
 *
 * 本任务只落**框架三件**（框架本体 / 路由 / 状态）——实测宿主若共享 `element-plus`，
 * 插件会把整库以 share provider 块由宿主入口静态引入（+334.5 KB gzip，首屏超预算）；
 * UI 组件库与平台基座包（`@bms/core` / `@bms/ui-ep`，源码直出、宿主以 alias 消费、
 * MF 探测不到）的共享方案归 `02_02`（见详细设计 §3.3 / §7）。
 */
const SHARED_DEPENDENCIES: Record<string, { singleton: boolean }> = {
  vue: { singleton: true },
  'vue-router': { singleton: true },
  pinia: { singleton: true },
}

// 演示模块工程（MF remote）：独立构建、产物独立（dist/ 不并入主应用产物）；
// 宿主经模块清单在运行期注册并加载本容器暴露的模块定义。
export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: MODULE_NAME,
      filename: REMOTE_ENTRY_FILE,
      exposes: { [EXPOSE_KEY]: './src/index.ts' },
      shared: SHARED_DEPENDENCIES,
    }),
  ],
  build: {
    // MF 依赖顶层 await 与动态导入；无历史浏览器包袱，取 esnext
    target: 'esnext',
  },
  server: {
    port: PORT,
    strictPort: true,
    // 跨端口加载：放开 CORS 并声明自身 origin（remoteEntry 内部资源 URL 依据）
    cors: true,
    origin: `http://localhost:${String(PORT)}`,
  },
  preview: {
    port: PORT,
    strictPort: true,
    cors: true,
  },
})
