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
 * @returns 模块目录名。
 */
function moduleNameOf(path: string): string {
  return path.slice(ENTRY_PREFIX.length, path.length - ENTRY_SUFFIX.length)
}

/**
 * 由 glob 表构建入口懒加载表（键归一为模块目录名）。
 *
 * `import.meta.glob` 由 Vite 在**转换期**解析且结果随转换缓存固化（运行期改文件系统不会重扫），
 * 故把键归一抽为纯函数，供用例注入合成 glob 表直接断言。
 *
 * @param glob glob 表（构建期枚举产物；用例可注入合成表）。
 * @returns 入口懒加载表（模块目录名 → 入口加载器）。
 */
export function buildModuleEntryTable(glob: ModuleEntryTable): ModuleEntryTable {
  return Object.fromEntries(
    Object.entries(glob).map(([path, load]): [string, () => Promise<ModuleEntryModule>] => [
      moduleNameOf(path),
      load,
    ]),
  )
}

/** 模块入口懒加载表（模块目录名 → 入口加载器）。 */
export const MODULE_ENTRIES: ModuleEntryTable = buildModuleEntryTable(entries)

/** 本地形态入口解析器（入口标识未登记即拒绝加载）。 */
export const resolveLocalModuleEntry: ModuleEntryResolver = createModuleEntryTableResolver(MODULE_ENTRIES)
