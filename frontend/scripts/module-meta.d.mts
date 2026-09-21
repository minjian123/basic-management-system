/**
 * `module-meta.mjs` 的类型声明（供模块工程构建配置在 TS 下直接引用；纯类型，无运行期产物）。
 */

/** 模块工程 `package.json` 的最小面。 */
export interface ModulePackage {
  /** 包名（`@bms/module-<模块名>`）。 */
  name: string
  /** 版本（模块版本单一来源）。 */
  version: string
}

/** 产物元数据（`dist/module.meta.json`）。 */
export interface ModuleMeta {
  /** 模块名（= 清单 `name`）。 */
  name: string
  /** 版本（= 模块工程 `package.json` 版本）。 */
  version: string
  /** 契约版本（= 平台常量）。 */
  contractVersion: number
}

/** 产物元数据文件名（发布与护栏的「产物版本」权威）。 */
export const MODULE_META_FILE: string

/** 构建期注入的版本常量名（模块定义经它取得 `package.json` 版本）。 */
export const MODULE_VERSION_DEFINE: string

/** 模块契约版本单一来源文件名（`frontend/module-contract.json`）。 */
export const MODULE_CONTRACT_FILE: string

/** 读取模块工程 `package.json`。 */
export function loadModulePackage(moduleDir: string): ModulePackage

/** 生成构建期版本注入（`define`，vite / vitest 同用）。 */
export function moduleVersionDefine(version: string): Record<string, string>

/** 读取平台模块契约版本（单一来源 `frontend/module-contract.json`）。 */
export function loadModuleContractVersion(frontendDir?: string): number

/** 产物元数据插件（构建结束 emit `module.meta.json`）。 */
export function createModuleMetaPlugin(options: {
  name: string
  version: string
  contractVersion: number
}): { name: string; apply: 'build'; generateBundle: () => void }
