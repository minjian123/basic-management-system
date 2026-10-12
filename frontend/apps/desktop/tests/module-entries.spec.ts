// kiwi_id: 977
/**
 * 本地模块入口解析器用例（01_02 / Kiwi 977）：`import.meta.glob` 懒加载表的键归一
 * （`../modules/<模块>/index.ts` → 模块目录名）与「入口标识未登记即拒绝加载」。
 *
 * `import.meta.glob` 由 Vite 在**转换期**解析且结果随转换缓存固化，故「运行期建目录再等重扫」
 * 不可靠（CI 上该文件所在 worker 可能已先转换过入口模块）；本用例改为向 `buildModuleEntryTable`
 * 注入**合成 glob 表**直接断言键归一，另对真实表断言未登记入口被拒。
 */

import { describe, expect, it } from 'vitest'

import { createModuleEntryTableResolver, type ModuleEntryModule, type ModuleEntryTable } from '@bms/core'

import { buildModuleEntryTable, resolveLocalModuleEntry } from '@/module/entries'

/** 合成 glob 键的模块目录名（唯一前缀，避免与真实模块冲突）。 */
const FIXTURE_NAME = 'zz-local-entry-probe'

/** 合成入口加载器（返回最小入口模块）。 */
async function loadProbe(): Promise<ModuleEntryModule> {
  return { default: {} }
}

describe('本地模块入口解析器（Kiwi 977）', () => {
  it('glob 键归一为模块目录名并可用；未登记入口拒绝加载', async () => {
    // 键取模块目录名（去掉 `../modules/` 前缀与 `/index.ts` 后缀），值为原加载器。
    const table: ModuleEntryTable = buildModuleEntryTable({
      [`../modules/${FIXTURE_NAME}/index.ts`]: loadProbe,
    })
    expect(Object.keys(table)).toEqual([FIXTURE_NAME])
    expect(table[FIXTURE_NAME]).toBe(loadProbe)

    // 已登记入口按 `entry` 键解析出入口模块；未登记入口拒绝加载（防静默降级）。
    const entry = { name: FIXTURE_NAME, entry: FIXTURE_NAME, version: '1.0.0', mode: 'local', enabled: true } as const
    const resolver = createModuleEntryTableResolver(table)
    await expect(resolver(entry)).resolves.toEqual({ default: {} })
    await expect(resolver({ ...entry, entry: 'not-registered' })).rejects.toThrow('模块入口未登记')

    // 真实表（宿主当前无存量本地模块）：入口表按构建期枚举装配，未登记入口同样被拒。
    await expect(resolveLocalModuleEntry({ ...entry, entry: 'not-registered' })).rejects.toThrow('模块入口未登记')
  })
})
