import { fileURLToPath, URL } from 'node:url'

import { federation } from '@module-federation/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

import {
  createModuleMetaPlugin,
  loadModuleContractVersion,
  loadModulePackage,
  moduleVersionDefine,
} from '../../scripts/module-meta.mjs'
import { loadSharedDependencies } from '../../scripts/shared-deps.mjs'

/** 模块名（= 模块清单 `name` = MF 容器名；见任务 02_01 详细设计 §3.3 远端命名约定）。 */
const MODULE_NAME = 'demo'

/** 远端容器入口文件名（契约常量 `MODULE_REMOTE_ENTRY_FILE` 同值，构建期须一致）。 */
const REMOTE_ENTRY_FILE = 'remoteEntry.js'

/** 暴露键（契约常量 `MODULE_EXPOSE_KEY` 同值；模块定义默认导出）。 */
const EXPOSE_KEY = './module'

/** 固定预览端口（发布存储服务默认端口，演示清单指向版本目录）。 */
const PORT = 5002

/** 模块工程目录（版本单一来源：`package.json`）。 */
const MODULE_DIR = fileURLToPath(new URL('.', import.meta.url))

/** 模块版本（构建期注入模块定义，定义不再手写版本）。 */
const MODULE_VERSION = loadModulePackage(MODULE_DIR).version

/** 平台模块契约版本（单一来源 `frontend/module-contract.json`）。 */
const CONTRACT_VERSION = loadModuleContractVersion()

/**
 * Module Federation 共享依赖（**单例 + 版本要求**）：与宿主同源——共享面与 `requiredVersion`
 * 取自单一来源 `frontend/shared-dependencies.json`（不得各写一份）。
 *
 * 模块为**消费方**（`role: 'remote'`）：每项带 `import: false`（**不打包本地回退副本**）
 * 与 `strictVersion: true`（版本不满足即拒绝加载）——宁可加载失败，不要静默出现第二份实例
 * （见任务 02_02 详细设计 §3.3）。
 */
const { shared: SHARED_DEPENDENCIES } = loadSharedDependencies({ role: 'remote' })

// 演示模块工程（MF remote）：独立构建、产物独立（dist/ 不并入主应用产物）；
// 宿主经模块清单在运行期注册并加载本容器暴露的模块定义。
//
// **两个构建目标**（`--mode standalone` 切换；见任务 02_02 详细设计 §3.3）：
//   - 缺省（`remote`）→ `dist/`：**远端产物**，只含 MF 容器与暴露的模块定义及其异步分包，
//     入口显式声明为 `src/index.ts`、**不带 HTML 壳**——独立预览壳自带一份框架本地副本，
//     若并入同一构建图，会被宿主在加载暴露模块时按依赖提示一并预下载（白下载上百 KB）；
//   - `standalone` → `dist-standalone/`：**独立预览产物**，带 HTML 壳与本地框架副本，
//     供模块脱离宿主独立开发与预览（本目标下框架依赖本地提供，不走共享域）。
export default defineConfig(({ mode }) => {
  const isStandaloneBuild = mode === 'standalone'
  return {
    // 版本单一来源注入（模块定义经 `__BMS_MODULE_VERSION__` 取得 `package.json` 版本）
    define: moduleVersionDefine(MODULE_VERSION),
    plugins: [
      vue(),
      // 产物元数据（版本发现：发布与护栏据此校验「清单 = 产物 = 源码」）
      createModuleMetaPlugin({ name: MODULE_NAME, version: MODULE_VERSION, contractVersion: CONTRACT_VERSION }),
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
      outDir: isStandaloneBuild ? 'dist-standalone' : 'dist',
      // sourcemap：外部 `.map`（不内联源码），随发布按版本归档；线上异常可映射到源码位置
      sourcemap: true,
      // 远端产物显式声明入口（不带 HTML 壳）；独立预览目标沿用 HTML 入口
      rollupOptions: isStandaloneBuild
        ? {}
        : { input: { module: fileURLToPath(new URL('./src/index.ts', import.meta.url)) } },
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
  }
})
