/**
 * 护栏：基类清单对账（《前端基类清单》↔ 核心源码定义 ↔ 核心入口导出 ↔ 插件与宿主导入）。
 *
 * 双向校验五个面：
 * ① 漏登记 / 僵尸条目——清单登记集合与源码定义的基类集合零差集；
 * ② 僵尸位置——§2.1「已交付」条目的代码位置文件存在且定义该类；
 * ③ 继承口径——§2.1 父基类列与源码 `extends` 一致；
 * ④ 导出完整性——源码定义的基类均自核心入口具名导出；
 * ⑤ 使用合规——插件与宿主自 `@bms/core` 导入的基类均在清单登记。
 *
 * 落点登记见《前端基类清单》§12「维护约定」与《前端资产清单》B10。
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

/** 源码文件（路径 + 内容）：供纯函数式对账与 fixture 复用。 */
export interface SourceFile {
  /** 文件路径（对账输出用）。 */
  path: string
  /** 文件内容。 */
  source: string
}

/** §2.1 全量登记表的一行。 */
export interface ChecklistRow {
  /** 基类名。 */
  name: string
  /** 父基类列中出现的基类名（根为空数组）。 */
  parents: string[]
  /** 代码位置（相对 `core/src`）。 */
  location: string
  /** 状态列原文（`已交付` / `部分` / `占位` / `待交付`）。 */
  status: string
}

/** 源码定义：类名 → 所在文件与父基类。 */
export interface ClassDefinition {
  /** 相对根目录的文件路径。 */
  file: string
  /** `extends` 的父类名（无 `extends` 为空串）。 */
  parent: string
}

/** 非基类身份的类名（mixin 内部匿名类等），不参与清单对账。 */
export const NON_BASE_CLASSES: readonly string[] = ['BaseObjectMixed']

/** 父基类对账豁免：根无父；`BaseError` 经 mixin 实现多重继承（见清单 §6.3）。 */
export const PARENT_EXEMPT: readonly string[] = ['BaseObject', 'BaseError']

const CORE_ROOT = resolve(import.meta.dirname, '..')
const CORE_SRC = join(CORE_ROOT, 'src')
const CHECKLIST_PATH = resolve(CORE_ROOT, '../../../bms文档/前端基类清单.md')
/** 插件与宿主源码根（校验其对核心基类的使用是否均已登记）。 */
const PLUGIN_SRC_ROOTS = [
  resolve(CORE_ROOT, '../ui-ep/src'),
  resolve(CORE_ROOT, '../vue/src'),
  resolve(CORE_ROOT, '../../apps/desktop/src'),
]

/** 递归收集源码文件。 */
function sourceFiles(dir: string, extensions: readonly string[] = ['.ts']): SourceFile[] {
  const files: SourceFile[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      files.push(...sourceFiles(path, extensions))
    } else if (extensions.some((ext) => entry.endsWith(ext))) {
      files.push({ path, source: readFileSync(path, 'utf-8') })
    }
  }
  return files
}

/** 取文档章节内容（`start` 标题行到 `end` 标题行之间）。 */
function section(source: string, start: string, end: string): string {
  const from = source.indexOf(start)
  const to = source.indexOf(end)
  if (from < 0 || to <= from) {
    return ''
  }
  return source.slice(from, to)
}

/** 解析 §2.1 全量登记表（按列取基类名 / 父基类 / 代码位置 / 状态）。 */
export function parseChecklistRows(source: string): ChecklistRow[] {
  const rows: ChecklistRow[] = []
  for (const line of source.split('\n')) {
    if (!/^\|\s*\d+\s*\|/.test(line)) {
      continue
    }
    const cells = line.split('|').map((cell) => cell.trim())
    const name = (cells[2] ?? '').match(/^`(Base[A-Za-z0-9]+)`$/)?.[1]
    if (name === undefined) {
      continue
    }
    rows.push({
      name,
      parents: [...(cells[3] ?? '').matchAll(/`(Base[A-Za-z0-9]+)`/g)].map((match) => match[1] as string),
      location: (cells[6] ?? '').match(/`([^`]+)`/)?.[1] ?? '',
      status: cells[8] ?? '',
    })
  }
  return rows
}

/** 清单登记集合：§2.1 全量登记表 + §4 插件基类族与注册表。 */
export function parseChecklistRegistry(source: string): Set<string> {
  const names = new Set<string>()
  for (const row of parseChecklistRows(source)) {
    names.add(row.name)
  }
  const pluginFamily = section(source, '## 4. 插件基类族与注册表', '## 5.')
  for (const line of pluginFamily.split('\n')) {
    if (!line.startsWith('|')) {
      continue
    }
    for (const match of line.matchAll(/`(Base[A-Za-z0-9]+)`/g)) {
      names.add(match[1] as string)
    }
  }
  return names
}

/** 扫描源码中的基类定义（类名 → 文件与父基类）。 */
export function scanClassDefinitions(files: SourceFile[], root: string): Map<string, ClassDefinition> {
  const definitions = new Map<string, ClassDefinition>()
  for (const file of files) {
    for (const match of file.source.matchAll(/\bclass\s+(Base[A-Za-z0-9]+)(?:<[^>]*>)?\s*(?:extends\s+([A-Za-z0-9_.]+))?/g)) {
      const name = match[1] as string
      if (!definitions.has(name)) {
        definitions.set(name, { file: relative(root, file.path), parent: match[2] ?? '' })
      }
    }
  }
  return definitions
}

/** 双向差集（漏登记 / 僵尸条目）。 */
export function diffSets(left: Set<string>, right: Set<string>): { onlyLeft: string[]; onlyRight: string[] } {
  return {
    onlyLeft: [...left].filter((item) => !right.has(item)).sort(),
    onlyRight: [...right].filter((item) => !left.has(item)).sort(),
  }
}

/** 父基类口径不一致项（豁免项跳过）。 */
export function parentMismatches(
  rows: readonly ChecklistRow[],
  definitions: Map<string, ClassDefinition>,
  exempt: readonly string[] = PARENT_EXEMPT,
): string[] {
  const problems: string[] = []
  for (const row of rows) {
    if (exempt.includes(row.name)) {
      continue
    }
    const actual = definitions.get(row.name)?.parent ?? ''
    if (actual === '') {
      problems.push(`${row.name}: 源码未解析到 extends`)
      continue
    }
    if (!row.parents.includes(actual)) {
      problems.push(`${row.name}: 清单父为「${row.parents.join(' + ') || '—'}」，源码 extends ${actual}`)
    }
  }
  return problems
}

/** 核心入口具名导出的基类名（排除 `type` 导出与 `export *`）。 */
export function parseEntryExports(source: string): Set<string> {
  const names = new Set<string>()
  for (const block of source.matchAll(/export\s*(?:type\s*)?\{([^}]*)\}\s*from/g)) {
    for (const raw of (block[1] as string).split(',')) {
      const item = raw.trim()
      if (item === '' || item.startsWith('type ')) {
        continue
      }
      const name = item.split(/\s+as\s+/).pop()?.trim() ?? ''
      if (/^Base[A-Za-z0-9]+$/.test(name)) {
        names.add(name)
      }
    }
  }
  return names
}

/** 插件与宿主源码自 `@bms/core` 导入的基类名。 */
export function parseCoreImports(files: SourceFile[]): Set<string> {
  const names = new Set<string>()
  for (const file of files) {
    for (const match of file.source.matchAll(/import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g)) {
      if (!(match[2] as string).startsWith('@bms/core')) {
        continue
      }
      for (const raw of (match[1] as string).split(',')) {
        const item = raw.trim()
        if (item === '' || item.startsWith('type ')) {
          continue
        }
        const name = item.split(/\s+as\s+/)[0]?.trim() ?? ''
        if (/^Base[A-Za-z0-9]+$/.test(name)) {
          names.add(name)
        }
      }
    }
  }
  return names
}

describe('基类清单对账护栏', () => {
  const checklist = readFileSync(CHECKLIST_PATH, 'utf-8')
  const registered = parseChecklistRegistry(checklist)
  const rows = parseChecklistRows(checklist)
  const definitions = scanClassDefinitions(sourceFiles(CORE_SRC), CORE_SRC)
  const defined = new Set([...definitions.keys()].filter((name) => !NON_BASE_CLASSES.includes(name)))

  it('① 清单登记与源码定义双向零差集（漏登记 / 僵尸条目）', () => {
    expect(registered.size).toBeGreaterThan(90)
    expect(defined.size).toBeGreaterThan(90)
    const { onlyLeft, onlyRight } = diffSets(registered, defined)
    expect(onlyLeft, `清单有而源码无（僵尸条目）：${onlyLeft.join(', ')}`).toEqual([])
    expect(onlyRight, `源码有而清单未登记（漏登记）：${onlyRight.join(', ')}`).toEqual([])
  })

  it('② §2.1 已交付条目的代码位置存在且定义该类（僵尸位置）', () => {
    const problems: string[] = []
    for (const row of rows) {
      if (!row.status.includes('已交付') || row.location === '') {
        continue
      }
      const path = join(CORE_SRC, row.location)
      if (!existsSync(path)) {
        problems.push(`${row.name}: 代码位置不存在 ${row.location}`)
        continue
      }
      if (!new RegExp(`\\bclass\\s+${row.name}\\b`).test(readFileSync(path, 'utf-8'))) {
        problems.push(`${row.name}: ${row.location} 中未定义该类`)
      }
    }
    expect(problems).toEqual([])
  })

  it('③ §2.1 父基类列与源码 extends 一致', () => {
    expect(parentMismatches(rows, definitions)).toEqual([])
  })

  it('④ 源码定义的基类均自核心入口具名导出', () => {
    const exported = parseEntryExports(readFileSync(join(CORE_SRC, 'index.ts'), 'utf-8'))
    expect(exported.size).toBeGreaterThan(90)
    const missing = [...defined].filter((name) => !exported.has(name)).sort()
    expect(missing, `未自核心入口导出：${missing.join(', ')}`).toEqual([])
  })

  it('⑤ 插件与宿主自 @bms/core 导入的基类均在清单登记', () => {
    const files = PLUGIN_SRC_ROOTS.flatMap((root) => sourceFiles(root, ['.ts', '.vue']))
    const imported = parseCoreImports(files)
    expect(imported.size).toBeGreaterThan(20)
    const missing = [...imported].filter((name) => !registered.has(name)).sort()
    expect(missing, `未登记：${missing.join(', ')}`).toEqual([])
  })

  it('⑥ fixture：漏登记 / 僵尸条目 / 父基类漂移均被拦截', () => {
    const probeFiles: SourceFile[] = [
      { path: 'probe.ts', source: 'export class BaseProbeSheet extends BasePlaceholderState {}\n' },
    ]
    const probeDefinitions = scanClassDefinitions(probeFiles, '.')

    expect(diffSets(new Set<string>(), new Set(probeDefinitions.keys())).onlyRight).toEqual(['BaseProbeSheet'])
    expect(diffSets(new Set(['BaseGhostEntry']), new Set<string>()).onlyLeft).toEqual(['BaseGhostEntry'])

    const drifted = parentMismatches(
      [{ name: 'BaseProbeSheet', parents: ['BaseComponent'], location: 'probe.ts', status: '已交付' }],
      probeDefinitions,
      [],
    )
    expect(drifted.length).toBeGreaterThan(0)
  })
})
