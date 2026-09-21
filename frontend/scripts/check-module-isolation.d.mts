/**
 * `check-module-isolation.mjs` 的类型声明（供宿主护栏用例在 TS 下直接引用；纯类型，无运行期产物）。
 */

/** 待检文件（展示路径 + 内容）。 */
export interface IsolationFile {
  /** 展示路径（真实扫描为相对 `frontend/` 的路径；fixture 为任意标识）。 */
  path: string
  /** 文件内容。 */
  source: string
}

/** 扫描一组源码文件（纯函数，供 fixture 断言）。 */
export function scanSourceFiles(files: IsolationFile[]): string[]

/** 扫描一组产物文件（纯函数；CSS 与模块自有 JS 块）。 */
export function scanProductFiles(input: { css?: IsolationFile[]; js?: IsolationFile[] }): string[]

/** 收集模块源码文件（模块工程 `src/**` + 宿主构建期合并模块目录）。 */
export function collectModuleSourceFiles(frontendDir?: string): IsolationFile[]

/** 收集单个模块工程的远端产物扫描目标。 */
export function collectProductTargets(moduleDir: string): { css: IsolationFile[]; js: IsolationFile[] }

/** 模块工程目录清单（`frontend/modules/*`，含 `package.json` 者）。 */
export function listModuleDirs(frontendDir?: string): string[]

/** 收集并扫描全部模块源码。 */
export function scanModuleSources(frontendDir?: string): string[]

/** 收集并扫描全部模块远端产物（无任何产物目录即抛错）。 */
export function scanModuleProducts(frontendDir?: string): string[]
