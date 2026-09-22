/**
 * `module-metrics.mjs` 的类型声明（纯类型，无运行期产物）。
 */

/** 远端容器入口文件名（与契约常量 `MODULE_REMOTE_ENTRY_FILE` 同值）。 */
export const REMOTE_ENTRY_FILE: string

/** 模块产物体积（入口闭包口径）。 */
export interface ModuleSize {
  /** 入口闭包文件数。 */
  entryFiles: number
  /** 入口闭包 gzip 合计（KB，1 位小数）。 */
  entryGzipKb: number
  /** 入口闭包最大单块 gzip（KB，1 位小数）。 */
  largestGzipKb: number
  /** 入口外 JS 异步块数。 */
  asyncChunkCount: number
}

/** 递归收集产物目录下的 JS / CSS 文件。 */
export function walkDistFiles(distDir: string): string[]

/** 收集容器入口闭包（自 `remoteEntry.js` 出发）。 */
export function collectEntryClosure(distDir: string): Set<string>

/** 测量模块产物体积（缺产物入口返回 `undefined`）。 */
export function measureModuleDist(moduleDir: string): ModuleSize | undefined
