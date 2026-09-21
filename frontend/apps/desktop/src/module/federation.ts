/**
 * 远端模块入口解析器（宿主）：经 Module Federation 运行时按**模块清单**登记远端容器并加载其
 * 暴露的模块定义（暴露键 `./module`）。
 *
 * 只做「登记 + 加载」两件事，**不做形状与版本校验**——校验在清单驱动加载器内统一执行，
 * 保证本地形态与远端形态走同一条校验链（见任务 02_01 详细设计 §3.2 / §3.3）。
 */

import { MODULE_EXPOSE_KEY, type ModuleEntryModule, type ModuleEntryResolver } from '@bms/core'
import { loadRemote, registerRemotes } from '@module-federation/runtime'

/** 本地演示远端 origin（生产清单地址替换与版本发现归 `03_02`）。 */
export const MODULE_REMOTE_ORIGIN = 'http://localhost:5002'

/**
 * 远端入口类型：Vite 模块产物为 **ESM**（`remoteEntry.js` 具名导出 `init` / `get`），
 * 运行期登记须显式声明 `module`——缺省会被当作经典脚本容器处理，
 * 表现为 `#RUNTIME-001 Failed to get remoteEntry exports`（2026-09-21 实测）。
 */
export const MODULE_REMOTE_ENTRY_TYPE = 'module'

/**
 * 创建远端入口解析器（Module Federation 运行时）。
 *
 * @returns 入口解析器。
 */
export function createFederationEntryResolver(): ModuleEntryResolver {
  return async (entry): Promise<ModuleEntryModule> => {
    // 同名以清单为准重登记（`installModules` 可重入，`force` 保证幂等）
    registerRemotes([{ name: entry.name, entry: entry.entry, type: MODULE_REMOTE_ENTRY_TYPE }], { force: true })
    const loaded = (await loadRemote(`${entry.name}/${MODULE_EXPOSE_KEY}`)) as ModuleEntryModule | undefined
    return loaded ?? {}
  }
}
