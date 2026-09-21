/**
 * 模块入口懒加载表：以模块目录名索引应用内模块入口（Vite 依动态导入自动分包）。
 *
 * 清单 `entry` 即本表键——清单驱动加载、不硬编码模块地址；远端形态（Module Federation）
 * 由 `02_01` 接入后以远端入口替换本表解析。
 */

import type { ModuleEntryModule, ModuleEntryTable } from '@bms/core'

/** 模块入口模块集合（构建期枚举，运行期按需加载）。 */
const entries = import.meta.glob<ModuleEntryModule>('../modules/*/index.ts')

/** 入口路径前缀 / 后缀（glob 键形如 `../modules/demo/index.ts`）。 */
const ENTRY_PREFIX = '../modules/'
const ENTRY_SUFFIX = '/index.ts'

/**
 * 由 glob 键取模块目录名。
 *
 * @param path glob 键。
 */
function moduleNameOf(path: string): string {
  return path.slice(ENTRY_PREFIX.length, path.length - ENTRY_SUFFIX.length)
}

/** 模块入口懒加载表（模块目录名 → 入口加载器）。 */
export const MODULE_ENTRIES: ModuleEntryTable = Object.fromEntries(
  Object.entries(entries).map(([path, load]) => [moduleNameOf(path), load]),
)
