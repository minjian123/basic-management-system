/**
 * 本地模块入口解析器（宿主，构建期合并形态）：以模块目录名索引应用内模块入口
 * （Vite 依动态导入自动分包）。
 *
 * 清单 `entry` 即本表键——本地形态的模块（未迁移模块）随宿主构建发布；运行时远端形态
 * 由 `./federation.ts` 的远端解析器承接（两者经 `host.ts` 按清单 `mode` 分派）。
 * 当前无存量本地模块，故目录为空、表为空（能力保留、由用例覆盖）。
 */

import {
  createModuleEntryTableResolver,
  type ModuleEntryModule,
  type ModuleEntryResolver,
  type ModuleEntryTable,
} from '@bms/core'

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

/** 本地形态入口解析器（入口标识未登记即拒绝加载）。 */
export const resolveLocalModuleEntry: ModuleEntryResolver = createModuleEntryTableResolver(MODULE_ENTRIES)
