// kiwi_id: 2295, 2296
/**
 * 件族样式齐备护栏（11_01 交互类 / 11_02 容器与展示反馈件族样式补齐 · 需求 11-1）：
 * **硬断言全库真裸骨架件**均含非空 `<style scoped>`，且样式块无硬编码色值（一律消费令牌）。
 *
 * 口径（需求 11-1 §2.5）：
 * - **真裸骨架件**：模板含自绘 DOM（`div` / `span` / `button` / `input` / `select` 等）且无样式块 → **必须补齐**；
 * - **EP 薄包装**：根元素即 Element Plus 件、无自绘 DOM，靠组件库全局样式已正常 → **豁免**（显式清单 + 理由）。
 *
 * 按用户口径（2026-10-14 拍板）：本护栏**对全库真裸骨架件硬断言、不留批次豁免**——`11_01` 补交互类 17 件、
 * `11_02` 补容器与展示反馈 18 件，其余随 `11_03` / `11_04` 补齐，**在此之前本用例按设计持续红**（门禁红即
 * 「全库尚未补齐」的真实反映；不得以豁免清单掩盖）。
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { basename, join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const COMPONENTS = resolve(process.cwd(), 'src/components')

/** 色值字面量（十六进制 / rgb[a] / hsl[a]）。 */
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(/

/** 组件内样式块（`<style scoped>` ... `</style>`）。 */
const STYLE_BLOCK = /<style scoped>([\s\S]*?)<\/style>/

/**
 * EP 薄包装豁免清单（根元素即 Element Plus 件、无自绘 DOM）。
 *
 * 逐件理由：件根元素直接是 Element Plus 件，无任何自绘 DOM，呈现完全由组件库全局样式（`element-plus/dist/index.css`
 * 经宿主 `src/styles/index.ts` 引入）承担，补 `<style scoped>` 反而会与组件库外观重复定义。
 */
const THIN_WRAPPERS: Readonly<Record<string, string>> = {
  'feedback/SkeletonBlock': '根元素 `el-skeleton`（骨架屏，形态完全由组件库承担）',
  'input/TextInput': '根元素 `el-input`（单行文本，无自绘 DOM）',
  'input/TextareaInput': '根元素 `el-input`（多行文本，无自绘 DOM）',
  'input/NumberInput': '根元素 `el-input-number`（无自绘 DOM）',
  'input/SelectInput': '根元素 `el-select`（无自绘 DOM）',
  'input/RadioInput': '根元素 `el-segmented` / `el-radio-group`（无自绘 DOM）',
  'input/SwitchInput': '根元素 `el-switch`（无自绘 DOM）',
  'input/BooleanCheckbox': '根元素 `el-checkbox`（无自绘 DOM）',
  'modal/FormDialog': '根元素 `el-dialog`（表单对话框壳，无自绘 DOM）',
  'modal/FormDrawer': '根元素 `el-drawer`（表单抽屉壳，无自绘 DOM）',
}

/** `11_01` 补齐的交互类 17 件。 */
const INTERACTION_BATCH = [
  'interaction/PermissionConfig',
  'interaction/MenuPermissionPanel',
  'interaction/PermissionTree',
  'interaction/FormPermissionPanel',
  'interaction/ActionPermissionPanel',
  'interaction/FieldPermissionPanel',
  'interaction/DataScopePanel',
  'interaction/DynamicDictPicker',
  'interaction/RoleAssignPanel',
  'interaction/IconPicker',
  'interaction/IconLibrary',
  'interaction/CodeEditor',
  'interaction/CodeMirrorHost',
  'interaction/CodeViewer',
  'interaction/CronEditor',
  'interaction/ExpressionEditor',
  'interaction/SqlEditor',
]

/** `11_02` 补齐的容器与展示反馈 18 件（容器族 8 + 展示族 7 + 反馈族 3）。 */
const CONTAINER_DISPLAY_FEEDBACK_BATCH = [
  'container/AspectRatioContainer',
  'container/AutoHeightContainer',
  'container/FullscreenContainer',
  'container/LazyContainer',
  'container/ScrollContainer',
  'container/SectionContainer',
  'container/StatusContainer',
  'container/VirtualListContainer',
  'display/AuditDiff',
  'display/FilePreview',
  'display/QrCode',
  'display/QuickEntry',
  'display/UserAvatar',
  'display/UserInfo',
  'display/WatermarkOverlay',
  'feedback/EmptyState',
  'feedback/ErrorPage',
  'feedback/LoadingMask',
]

/** 全库组件源码（`<族>/<件名>` → 源码）。 */
function componentSources(): { name: string; path: string; source: string }[] {
  const result: { name: string; path: string; source: string }[] = []
  for (const family of readdirSync(COMPONENTS)) {
    const familyDir = join(COMPONENTS, family)
    if (!statSync(familyDir).isDirectory()) {
      continue
    }
    for (const entry of readdirSync(familyDir)) {
      if (!entry.endsWith('.vue')) {
        continue
      }
      const path = join(familyDir, entry)
      result.push({ name: `${family}/${basename(entry, '.vue')}`, path, source: readFileSync(path, 'utf8') })
    }
  }
  return result
}

/**
 * 取件模板段（首个 `<template>` 至最后一个 `</template>`）。
 *
 * @param source 单文件组件源码。
 * @returns 模板文本；无模板返回空串。
 */
function templateOf(source: string): string {
  const start = source.indexOf('<template>')
  const end = source.lastIndexOf('</template>')
  return start < 0 || end < start ? '' : source.slice(start, end)
}

/**
 * 取模板根元素标签名（跳过开标签行 / 注释与空白）。
 *
 * @param source 单文件组件源码。
 * @returns 根元素标签名；无自绘根元素返回空串。
 */
function rootElementOf(source: string): string {
  const template = templateOf(source)
  if (template === '') {
    return ''
  }
  // 跳过 `<template>` 开标签本身所在行，再从后续行找首个元素。
  const body = template.slice(template.indexOf('>') + 1)
  for (const line of body.split('\n')) {
    const matched = line.match(/^\s*<([a-z][a-z0-9-]*)/)
    if (matched !== null) {
      return matched[1]
    }
  }
  return ''
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

/** 无样式件的清单。 */
function bareComponents(): { name: string; path: string; source: string }[] {
  return componentSources().filter((file) => {
    const block = file.source.match(STYLE_BLOCK)
    return block === null || block[1].trim().length === 0
  })
}

describe('件族样式齐备护栏（全库真裸骨架硬断言 + EP 薄包装豁免）', () => {
  it('本批交互类 17 件齐备（需求 11-1 首批范围）', () => {
    const names = componentSources()
      .filter((file) => file.name.startsWith('interaction/'))
      .map((file) => file.name)
    for (const target of INTERACTION_BATCH) {
      expect(names, `缺少件 ${target}`).toContain(target)
    }
    expect(INTERACTION_BATCH).toHaveLength(17)
  })

  it('本批交互类 17 件均含非空 <style scoped>', () => {
    const sources = new Map(componentSources().map((file) => [file.name, file]))
    for (const name of INTERACTION_BATCH) {
      const file = sources.get(name)
      expect(file, `缺少件 ${name}`).toBeDefined()
      const block = file?.source.match(STYLE_BLOCK)
      expect(block, `${name} 缺 <style scoped>`).not.toBeNull()
      expect((block?.[1] ?? '').trim().length, `${name} 样式块为空`).toBeGreaterThan(0)
    }
  })

  it('本批容器与展示反馈 18 件齐备（需求 11-1 第二批范围）', () => {
    const names = componentSources().map((file) => file.name)
    for (const target of CONTAINER_DISPLAY_FEEDBACK_BATCH) {
      expect(names, `缺少件 ${target}`).toContain(target)
    }
    expect(CONTAINER_DISPLAY_FEEDBACK_BATCH).toHaveLength(18)
  })

  it('本批容器与展示反馈 18 件均含非空 <style scoped>', () => {
    const sources = new Map(componentSources().map((file) => [file.name, file]))
    for (const name of CONTAINER_DISPLAY_FEEDBACK_BATCH) {
      const file = sources.get(name)
      expect(file, `缺少件 ${name}`).toBeDefined()
      const block = file?.source.match(STYLE_BLOCK)
      expect(block, `${name} 缺 <style scoped>`).not.toBeNull()
      expect((block?.[1] ?? '').trim().length, `${name} 样式块为空`).toBeGreaterThan(0)
    }
  })

  it('全库真裸骨架件均含非空 <style scoped>（硬断言、不留批次豁免）', () => {
    const offenders = bareComponents()
      .filter((file) => !(file.name in THIN_WRAPPERS))
      .map((file) => file.name)
    expect(
      offenders,
      `以下真裸骨架件缺 <style scoped>（11_02 ~ 11_04 待补，本断言按设计持续红直至全库补齐）：${offenders.join('、')}`,
    ).toEqual([])
  })

  it('EP 薄包装豁免清单与实际一致（清单漂移即失败）', () => {
    const actual = bareComponents()
      .filter((file) => rootElementOf(file.source).startsWith('el-'))
      .map((file) => file.name)
    expect([...actual].sort()).toEqual([...Object.keys(THIN_WRAPPERS)].sort())
    for (const [name, reason] of Object.entries(THIN_WRAPPERS)) {
      expect(reason.length, `${name} 豁免理由过短`).toBeGreaterThan(10)
    }
  })

  it('全库件族样式无硬编码色值（一律消费令牌）', () => {
    expect(scanColorLiterals(componentSources())).toEqual([])
  })

  it('fixture 违规被拦截（十六进制 / rgba / 空样式块）', () => {
    const problems = scanColorLiterals([
      { path: 'probe.vue', source: '<template><i /></template>\n<style scoped>.a { color: #ffffff; }</style>' },
      {
        path: 'probe2.vue',
        source: '<template><i /></template>\n<style scoped>.b { background: rgba(0, 0, 0, 0.1); }</style>',
      },
    ])
    expect(problems).toHaveLength(2)

    const empty = { path: 'probe3.vue', source: '<template><div /></template>\n<style scoped>\n</style>' }
    expect(scanColorLiterals([empty])).toEqual([])
    const block = empty.source.match(STYLE_BLOCK)
    expect((block?.[1] ?? '').trim().length).toBe(0)
  })

  it('无样式块 / 令牌消费不误判', () => {
    expect(
      scanColorLiterals([
        { path: 'probe.vue', source: '<template><i /></template>' },
        { path: 'probe2.vue', source: '<style scoped>.c { color: var(--bms-color-text); }</style>' },
      ]),
    ).toEqual([])
  })

  it('fixture 根元素识别与裸骨架判定', () => {
    expect(rootElementOf('<template>\n  <el-input />\n</template>')).toBe('el-input')
    expect(rootElementOf('<template>\n  <div class="x" />\n</template>')).toBe('div')
    expect(rootElementOf('<template>\n  <!-- 注释 -->\n  <section />\n</template>')).toBe('section')
    expect(rootElementOf('无模板')).toBe('')
  })

  it('相对路径工具（护栏自检：扫描面不为空）', () => {
    expect(componentSources().length).toBeGreaterThan(100)
    expect(relative(COMPONENTS, join(COMPONENTS, 'interaction', 'IconPicker.vue'))).toBe('interaction/IconPicker.vue')
  })
})
