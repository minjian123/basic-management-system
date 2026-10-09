// kiwi_id: 2238
// kiwi_id: 2260
/** 护栏：宿主页不直连具体插件（宿主只经模块清单 + 具名插槽注册表接入；入口懒加载表为唯一例外）；含显式上下文注入宿主页。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

/** 宿主源码根（本文件位于 `frontend/apps/desktop/tests/`）。 */
const SRC = resolve(process.cwd(), 'src')

/** 允许出现模块目录引用的宿主文件（模块入口懒加载表：唯一经清单接入的通路）。 */
const ALLOWED_FILES: readonly string[] = ['module/entries.ts']

/** 插件直连模式：`@bms/module-*` 包引入，或经相对 / 别名路径引入 `modules/<模块>/`。 */
const PLUGIN_IMPORT_PATTERN = /from\s*'(?:@bms\/module-[^']+|(?:@\/|\.{1,2}\/)+modules\/[^']+)'/

/**
 * 递归收集目录下指定后缀的文件。
 *
 * @param dir 目录。
 * @param suffix 后缀（如 `.vue`）。
 */
function walk(dir: string, suffix: string): string[] {
  const result: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      result.push(...walk(path, suffix))
    } else if (path.endsWith(suffix)) {
      result.push(path)
    }
  }
  return result
}

/**
 * 判定源码是否直连具体插件。
 *
 * @param source 源码文本。
 */
function connectsPlugin(source: string): boolean {
  return PLUGIN_IMPORT_PATTERN.test(source)
}

describe('具名插槽宿主隔离护栏（Kiwi 2238）', () => {
  it('宿主源码不直连具体插件（无 @bms/module-* / modules/* 引入）', () => {
    const files = [...walk(SRC, '.ts'), ...walk(SRC, '.vue')]
    expect(files.length).toBeGreaterThan(20)

    const offenders = files
      .filter((file) => !ALLOWED_FILES.some((allowed) => file.endsWith(allowed)))
      .filter((file) => connectsPlugin(readFileSync(file, 'utf8')))

    expect(offenders, `以下宿主文件直连了具体插件：${offenders.join(', ')}`).toEqual([])
  })

  it('fixture 违规被拦截（两种直连形态），合法用法不误判', () => {
    expect(connectsPlugin("import Sample from '@bms/module-sample'")).toBe(true)
    expect(connectsPlugin("import Tab from '../../modules/slot-sample/src/components/SlotTab.vue'")).toBe(true)
    expect(connectsPlugin("import Tab from '@/modules/slot-sample/src/index'")).toBe(true)

    expect(connectsPlugin("import { ModuleAreaOutlet } from '@bms/ui-ep'")).toBe(false)
    expect(connectsPlugin("const entries = import.meta.glob('../modules/*/index.ts')")).toBe(false)
  })

  it('用户详情宿主页经区域插槽件声明具名插槽（不硬编码插件）', () => {
    const source = readFileSync(join(SRC, 'views', 'SysUserDetailView.vue'), 'utf8')

    expect(source).toContain('module-area-outlet')
    expect(source).toContain('sys.user.detail.tabs')
    expect(source).not.toMatch(/@bms\/module-/)
  })

  it('角色分配页签经区域插槽件声明挂接位并注入只读上下文（roleId，非路由承载页）', () => {
    const source = readFileSync(join(SRC, 'views', 'system', 'role', 'RoleAssignTab.vue'), 'utf8')

    expect(source).toContain('module-area-outlet')
    expect(source).toContain('sys.role.detail.assign')
    expect(source).toContain(':context="slotContext"')
    expect(source).toContain('props.roleId')
    expect(source).toContain('registerSubmitter')
    expect(source).not.toMatch(/@bms\/module-/)
  })

  it('模块入口懒加载表是唯一出现模块目录引用的宿主文件', () => {
    const files = walk(SRC, '.ts')
    const referencing = files.filter((file) => readFileSync(file, 'utf8').includes('../modules/'))

    expect(referencing.length).toBe(1)
    expect(referencing[0].endsWith('module/entries.ts')).toBe(true)
  })
})
