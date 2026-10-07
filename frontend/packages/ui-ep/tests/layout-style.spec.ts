// kiwi_id: 2241, 2248
/** 布局族样式齐备护栏（06_01 / 02_03）：19 件均有非空 `<style scoped>`，且样式无硬编码色值（一律消费令牌）。 */

import { readFileSync, readdirSync } from 'node:fs'
import { basename, join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const LAYOUT_DIR = resolve(process.cwd(), 'src/components/layout')

/**
 * 布局族 19 件（需求 07-9 冻结 18 件 + 02_03 新增 `FormFrame`）。
 *
 * `FormFrame`（表单框架：列表 Tab + 记录 Tab）随 02_03 角色管理落地，属布局族**新增件**，
 * 一并纳入本护栏（样式齐备 + 无硬编码色值）。
 */
const LAYOUT_COMPONENTS = [
  'MainLayout',
  'SideMenu',
  'SideMenuItem',
  'TabNavBar',
  'TabNavContextMenu',
  'ContentTabs',
  'LayoutCard',
  'PageContainer',
  'CollapsePanel',
  'CollapsePanelGroup',
  'GridLayout',
  'GridItem',
  'SplitPane',
  'TreeMasterDetail',
  'DualTabs',
  'FormLayoutShell',
  'FormFrame',
  'SpacingDivider',
  'ModuleAreaOutlet',
]

/** 色值字面量（十六进制 / rgb[a] / hsl[a]）。 */
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(/

/** 组件内样式块（`<style scoped>` ... `</style>`）。 */
const STYLE_BLOCK = /<style scoped>([\s\S]*?)<\/style>/

/** 布局族件源码。 */
function layoutSources(): { name: string; path: string; source: string }[] {
  return readdirSync(LAYOUT_DIR)
    .filter((entry) => entry.endsWith('.vue'))
    .map((entry) => ({
      name: basename(entry, '.vue'),
      path: join(LAYOUT_DIR, entry),
      source: readFileSync(join(LAYOUT_DIR, entry), 'utf8'),
    }))
}

/**
 * 扫描样式块中的硬编码色值。
 *
 * @param files 文件清单。
 * @returns 违规项。
 */
function scanColorLiterals(files: { path: string; source: string }[]): string[] {
  const problems: string[] = []
  for (const file of files) {
    const block = file.source.match(STYLE_BLOCK)
    if (block === null) {
      continue
    }
    const style = block[1].replace(/\/\*[\s\S]*?\*\//g, '')
    const hit = style.match(COLOR_LITERAL)
    if (hit !== null) {
      problems.push(`${file.path}：样式硬编码色值 ${hit[0]}`)
    }
  }
  return problems
}

describe('布局族样式齐备护栏', () => {
  it('布局族 19 件齐备（需求冻结 18 件 + 02_03 新增 FormFrame）', () => {
    const names = layoutSources().map((file) => file.name)
    expect([...names].sort()).toEqual([...LAYOUT_COMPONENTS].sort())
  })

  it('每件均含非空 <style scoped>', () => {
    for (const file of layoutSources()) {
      const block = file.source.match(STYLE_BLOCK)
      expect(block).not.toBeNull()
      expect((block?.[1] ?? '').trim().length).toBeGreaterThan(0)
    }
  })

  it('布局族样式无硬编码色值（一律消费令牌）', () => {
    expect(scanColorLiterals(layoutSources())).toEqual([])
  })

  it('fixture 违规被拦截（十六进制 / rgba）', () => {
    const problems = scanColorLiterals([
      { path: 'probe.vue', source: '<template><i /></template>\n<style scoped>.a { color: #ffffff; }</style>' },
      {
        path: 'probe2.vue',
        source: '<template><i /></template>\n<style scoped>.b { background: rgba(0, 0, 0, 0.1); }</style>',
      },
    ])
    expect(problems).toHaveLength(2)
  })

  it('无样式块 / 令牌消费不误判', () => {
    expect(
      scanColorLiterals([
        { path: 'probe.vue', source: '<template><i /></template>' },
        { path: 'probe2.vue', source: '<style scoped>.c { color: var(--bms-color-text); }</style>' },
      ]),
    ).toEqual([])
  })
})
