/**
 * `release-module.mjs` 的类型声明（供宿主用例在 TS 下直接引用；纯类型，无运行期产物）。
 */

/** 清单条目（脚本侧形态，与 core `ModuleManifestEntry` 同形）。 */
export interface ManifestEntry {
  /** 模块名。 */
  name: string
  /** 入口（local 为源码标识；remote 为远端入口 URL）。 */
  entry: string
  /** 版本。 */
  version: string
  /** 加载形态。 */
  mode: 'local' | 'remote'
  /** 可见性（缺省 true）。 */
  enabled: boolean
}

/** 清单被拒项。 */
export interface ManifestRejection {
  /** 模块名（缺名时为空串）。 */
  name: string
  /** 拒绝原因。 */
  reason: string
}

/** 发布记录条目。 */
export interface ReleaseRecord {
  /** 时间（ISO，UTC）。 */
  at: string
  /** 操作者。 */
  by: string
  /** 动作。 */
  action: 'publish' | 'republish' | 'rollback' | 'disable' | 'enable'
  /** 模块名。 */
  module: string
  /** 版本。 */
  version: string
  /** 前版本（无则 null）。 */
  previousVersion: string | null
  /** 入口 URL。 */
  entry: string
  /** 契约版本（停用 / 启用为 null）。 */
  contractVersion: number | null
}

/** 发布记录文件结构。 */
export interface ReleaseLog {
  /** 结构版本。 */
  version: number
  /** 记录（追加式）。 */
  records: ReleaseRecord[]
}

/** 发布前强校验结果。 */
export interface ReleaseGuardResult {
  /** 违规清单（空即通过）。 */
  violations: string[]
  /** 产物元数据（缺失 / 非法为 undefined）。 */
  meta: { name: string; version: string; contractVersion: number } | undefined
  /** 模块工程 package.json。 */
  pkg: { name: string; version: string } | undefined
  /** 模块工程目录。 */
  moduleDir: string
  /** 产物目录。 */
  distDir: string
}

/** 清单文件（相对 frontend/）。 */
export const MANIFEST_PATH: string
/** 发布存储目录（相对 frontend/）。 */
export const RELEASES_DIR: string
/** 发布记录文件名（JSON 真源）。 */
export const RELEASE_LOG_FILE: string
/** 发布记录 Markdown 摘要文件名。 */
export const RELEASE_LOG_MARKDOWN_FILE: string
/** 远端容器入口文件名。 */
export const REMOTE_ENTRY_FILE: string
/** 缺省发布基址。 */
export const DEFAULT_ORIGIN: string
/** 合法加载形态。 */
export const LOAD_MODES: string[]
/** 模块名模式。 */
export const MODULE_NAME_PATTERN: RegExp
/** 远端入口 URL 模式。 */
export const REMOTE_ENTRY_PATTERN: RegExp
/** 合法发布记录动作。 */
export const RELEASE_ACTIONS: string[]

/** 发布流程错误（可读信息）。 */
export class ReleaseError extends Error {}

/** 解析模块清单（严格；口径与 core 一致）。 */
export function parseManifest(raw: unknown): { entries: ManifestEntry[]; rejected: ManifestRejection[] }

/** 读取清单文件（`entries` 归一；`raw` 为原始数组，写回时只改目标条目）。 */
export function readManifest(root?: string): {
  entries: ManifestEntry[]
  rejected: ManifestRejection[]
  raw: unknown[]
}

/** 写回清单（2 空格缩进 + 末尾换行；未涉及条目与字段原值保留）。 */
export function writeManifest(root: string, entries: unknown[]): void

/** 读取发布记录（缺省空记录）。 */
export function readReleaseLog(root?: string): ReleaseLog

/** 渲染发布记录 Markdown 摘要。 */
export function renderReleaseLogMarkdown(log: ReleaseLog): string

/** 追加发布记录（JSON 真源 + Markdown 摘要）。 */
export function appendReleaseLog(root: string, record: ReleaseRecord): void

/** 读取产物元数据（`dist/module.meta.json`）。 */
export function readModuleMeta(moduleDir: string): { name: string; version: string; contractVersion: number } | undefined

/** 取 URL 的 origin。 */
export function originOf(url: string): string | undefined

/** 取缺省操作者（git config user.name > USER）。 */
export function defaultOperator(root?: string): string

/** 发布前强校验三关（版本 / 隔离 / 共享）。 */
export function checkReleaseGuards(options: { root?: string; name: string }): ReleaseGuardResult

/** 取发布记录中该模块的上一个版本。 */
export function previousVersionOf(log: ReleaseLog, name: string, currentVersion: string): string | undefined

/** 发布模块（三关校验 → 归档 → 清单更新 → 发布记录）。 */
export function publishModule(options: {
  root?: string
  name: string
  origin?: string
  by?: string
  force?: boolean
  dryRun?: boolean
}): {
  action: 'publish' | 'republish'
  version: string
  entry: string
  archiveDir: string
  previousVersion: string | null
  dryRun?: boolean
  pkgVersion?: string
}

/** 回滚模块（清单版本回退；模块产物保留）。 */
export function rollbackModule(options: { root?: string; name: string; to?: string; by?: string }): {
  version: string
  previousVersion: string
  entry: string
}

/** 停用 / 启用模块（清单 `enabled`）。 */
export function setModuleEnabled(options: {
  root?: string
  name: string
  enabled: boolean
  by?: string
}): { enabled: boolean; version: string }

/** 模块状态（清单条目 / 已归档版本 / 最近记录）。 */
export function moduleStatus(options?: { root?: string; name?: string }): {
  entries: ManifestEntry[]
  rejected: ManifestRejection[]
  archived: Record<string, string[]>
  records: ReleaseRecord[]
}
