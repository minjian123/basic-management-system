/**
 * `check-module-manifest.mjs` 的类型声明（供宿主用例在 TS 下直接引用；纯类型，无运行期产物）。
 */

/** 契约用例文件名（相对模块工程目录）。 */
export const MODULE_CONTRACT_SPEC: string

/** 契约用例工厂标识（发现性护栏判据）。 */
export const MODULE_CONTRACT_FACTORY: string

/** 清单 / 版本发现 / sourcemap / 契约用例齐备护栏（纯函数）。 */
export function checkModuleManifest(options?: { frontendDir?: string }): string[]

/** 模块产物体积（入口闭包口径）。 */
export interface ModuleSizeSummaryEntry {
  /** 模块名。 */
  name: string
  /** 体积（缺产物入口为 `undefined`）。 */
  size:
    | {
        entryFiles: number
        entryGzipKb: number
        largestGzipKb: number
        asyncChunkCount: number
      }
    | undefined
}

/** 按模块产物体积汇总。 */
export function moduleSizeSummary(options?: { frontendDir?: string }): ModuleSizeSummaryEntry[]
