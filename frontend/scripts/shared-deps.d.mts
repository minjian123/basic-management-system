/**
 * `shared-deps.mjs` 的类型声明（供两侧构建配置在 TS 下直接引用单一来源；纯类型，无运行期产物）。
 */

/** 共享依赖声明条目（构建配置消费形态）。 */
export interface SharedDependencyEntry {
  /** 版本要求（semver 范围，取自依赖清单实装版本）。 */
  requiredVersion: string
  /** 单例（共享面内恒为真）。 */
  singleton: boolean
  /** 是否提供本地回退副本（消费方为 `false`——不打包第二份）。 */
  import?: false
  /** 抑制 `import: false` 的「无本地依赖」告警。 */
  suppressMissingImportWarning?: boolean
  /** 版本不满足即拒绝（消费方为真）。 */
  strictVersion?: boolean
  /** 是否随首屏直接引入（缺省不设）。 */
  eager?: boolean
}

/** 共享声明单一来源（`frontend/shared-dependencies.json`）结构。 */
export interface SharedSource {
  /** 共享域名称。 */
  shareScope?: string
  /** 共享面白名单（包名 → 声明）。 */
  shared: Record<string, Omit<SharedDependencyEntry, 'import' | 'suppressMissingImportWarning' | 'strictVersion'>>
  /** 消费方（模块侧）覆写项。 */
  remoteOverrides?: { import?: false; suppressMissingImportWarning?: boolean }
  /** 受控非共享项（含理由与体积阈值）。 */
  notShared?: Record<string, { reason: string; maxModuleGzipKb?: number }>
}

/** 构建角色：提供方（宿主）/ 消费方（模块）。 */
export type SharedRole = 'host' | 'remote'

/** 读取共享声明单一来源（原始结构）。 */
export function readSharedSource(): SharedSource

/** 生成构建配置用的 `shared` 声明（按角色追加形态差异）。 */
export function loadSharedDependencies(options?: { role?: SharedRole; root?: string }): {
  shareScope: string
  shared: Record<string, SharedDependencyEntry>
}

/** 共享面白名单（包名，声明序）。 */
export function sharedNames(): string[]

/** 受控非共享项（包名）。 */
export function notSharedNames(): string[]

/** 解析单一来源文件绝对路径。 */
export function resolveSourcePath(): string

/** 支持的角色取值。 */
export const SUPPORTED_ROLES: string[]
