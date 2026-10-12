// kiwi_id: 977
/**
 * 本地模块入口解析器用例（01_02 / Kiwi 977）：`import.meta.glob` 懒加载表的键归一
 * （`../modules/<模块>/index.ts` → 模块目录名）与「入口标识未登记即拒绝加载」。
 *
 * 宿主当前无存量本地模块，故用例在装载前于 `src/modules/` 下临时落一个同形目录
 * （`<模块>/index.ts`）驱动 glob 枚举，用毕即删（不留源码残留）。
 */

import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

/** 临时模块目录名（唯一前缀，避免与其他用例 / 真实模块冲突）。 */
const FIXTURE_NAME = 'zz-local-entry-probe'
/** 临时模块目录绝对路径。 */
const FIXTURE_DIR = join(process.cwd(), 'src', 'modules', FIXTURE_NAME)
/** 临时模块目录的父目录（仅在空目录时回收，避免误删真实本地模块）。 */
const MODULES_DIR = join(process.cwd(), 'src', 'modules')

/** 清临时模块目录（幂等；父目录非空则保留）。 */
function cleanup(): void {
  if (existsSync(FIXTURE_DIR)) {
    rmSync(FIXTURE_DIR, { recursive: true, force: true })
  }
  if (existsSync(MODULES_DIR) && readdirSync(MODULES_DIR).length === 0) {
    rmSync(MODULES_DIR, { recursive: true, force: true })
  }
}

afterEach(cleanup)

describe('本地模块入口解析器（Kiwi 977）', () => {
  it('glob 键归一为模块目录名并可用；未登记入口拒绝加载', async () => {
    cleanup()
    mkdirSync(FIXTURE_DIR, { recursive: true })
    writeFileSync(join(FIXTURE_DIR, 'index.ts'), 'export default { manifest: {}, setup: () => ({}) }\n')

    const { MODULE_ENTRIES, resolveLocalModuleEntry } = await import('@/module/entries')

    // 键取模块目录名（去掉 `../modules/` 前缀与 `/index.ts` 后缀），值为懒加载器。
    expect(Object.keys(MODULE_ENTRIES)).toContain(FIXTURE_NAME)
    const loader = MODULE_ENTRIES[FIXTURE_NAME]
    expect(typeof loader).toBe('function')
    await expect(loader?.()).resolves.toBeDefined()

    // 已登记入口按 `entry` 键解析出入口模块；未登记入口拒绝加载（防静默降级）。
    const entry = { name: FIXTURE_NAME, entry: FIXTURE_NAME, version: '1.0.0', mode: 'local', enabled: true } as const
    await expect(resolveLocalModuleEntry(entry)).resolves.toBeDefined()
    await expect(resolveLocalModuleEntry({ ...entry, entry: 'not-registered' })).rejects.toThrow('模块入口未登记')
  })
})
