/**
 * 清单对账（纯函数，可注入 fixture）：《前端基类清单》↔ 代码双向校验
 * （漏登记 / 僵尸条目 / depends 不一致 / 实现文件缺失）。
 */

import type { GuardProblem } from './ast'

/** 清单 §5 片段行 */
export interface ManifestFragmentRow {
  name: string
  key: string
  depends: string[]
}

/** 清单解析结果 */
export interface ManifestIndex {
  fragments: ManifestFragmentRow[]
  baseNames: string[]
  domainFiles: string[]
}

/** 代码侧索引 */
export interface CodeIndex {
  fragmentDepends: Record<string, string[]>
  /** 片段实现文件名（`useXxx.ts`） */
  fragmentFiles: string[]
  /** `src/base/` 导出类名 */
  baseExports: string[]
  /** 域基类包装路径（`src/components/base/<域>/BaseXxx.vue`） */
  domainFiles: string[]
}

function sectionOf(text: string, startPattern: RegExp, endPattern: RegExp): string {
  const lines = text.split('\n')
  const startIndex = lines.findIndex((line) => startPattern.test(line))
  if (startIndex < 0) {
    return ''
  }
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    if (endPattern.test(lines[index] ?? '')) {
      return lines.slice(startIndex, index).join('\n')
    }
  }
  return lines.slice(startIndex).join('\n')
}

/** 解析《前端基类清单》：§5 片段表 / §2 机制基类名 / §6 域基类实现文件 */
export function parseManifest(text: string): ManifestIndex {
  const fragments: ManifestFragmentRow[] = []
  for (const line of sectionOf(text, /^## 5\./, /^## 6\./).split('\n')) {
    const match = /^\|\s*`(use[A-Za-z0-9]+)`\s*\|\s*`([a-z0-9-]+)`\s*\|\s*([^|]*)\|/.exec(line)
    const name = match?.[1]
    const key = match?.[2]
    if (!name || !key) {
      continue
    }
    const depends = [...(match?.[3] ?? '').matchAll(/`([a-z0-9-]+)`/g)]
      .map((item) => item[1] ?? '')
      .filter((item) => item.length > 0)
    fragments.push({ name, key, depends })
  }

  const baseNames: string[] = []
  for (const line of sectionOf(text, /^## 2\./, /^## 3\./).split('\n')) {
    const cells = line.split('|').map((cell) => cell.trim())
    const role = cells[1] ?? ''
    if (!['根系', '组件根', '片段机制', '机制基类'].includes(role)) {
      continue
    }
    const baseCell = cells[2] ?? ''
    for (const match of baseCell.matchAll(/`(Base[A-Za-z0-9]+)(?:\.vue)?`/g)) {
      const name = match[1]
      if (name && !baseNames.includes(name)) {
        baseNames.push(name)
      }
    }
  }

  const domainFiles = [...sectionOf(text, /^## 6\./, /^## 7\./).matchAll(/`(Base[A-Za-z0-9]+\.vue)`/g)]
    .map((match) => match[1] ?? '')
    .filter((item) => item.length > 0)

  return { fragments, baseNames, domainFiles }
}

/** 双向对账：清单漏登记 / 僵尸条目 / depends 不一致 / 实现文件缺失 */
export function reconcileManifest(manifest: ManifestIndex, code: CodeIndex): GuardProblem[] {
  const problems: GuardProblem[] = []
  const manifestKeys = manifest.fragments.map((row) => row.key)
  const manifestFileNames = manifest.fragments.map((row) => `${row.name}.ts`)

  for (const row of manifest.fragments) {
    if (!(row.key in code.fragmentDepends)) {
      problems.push({
        file: '前端基类清单 §5',
        rule: 'manifest.fragment-missing',
        message: `清单片段「${row.key}」在 fragments.ts 缺失（僵尸条目）`,
      })
      continue
    }
    const codeDepends = code.fragmentDepends[row.key] ?? []
    const same = [...row.depends].sort().join(',') === [...codeDepends].sort().join(',')
    if (!same) {
      problems.push({
        file: '前端基类清单 §5',
        rule: 'manifest.fragment-depends',
        message: `片段「${row.key}」depends 不一致：清单 [${row.depends.join(', ')}] / 代码 [${codeDepends.join(', ')}]`,
      })
    }
    if (!code.fragmentFiles.includes(`${row.name}.ts`)) {
      problems.push({
        file: '前端基类清单 §5',
        rule: 'manifest.fragment-file',
        message: `片段「${row.name}」实现文件缺失`,
      })
    }
  }

  for (const key of Object.keys(code.fragmentDepends)) {
    if (!manifestKeys.includes(key)) {
      problems.push({
        file: 'src/components/base/fragments.ts',
        rule: 'manifest.fragment-unregistered',
        message: `片段「${key}」未在清单 §5 登记（漏登记）`,
      })
    }
  }
  for (const fileName of code.fragmentFiles) {
    if (!manifestFileNames.includes(fileName)) {
      problems.push({
        file: 'src/components/base',
        rule: 'manifest.fragment-file-unregistered',
        message: `片段实现「${fileName}」未在清单 §5 登记（漏登记）`,
      })
    }
  }

  for (const name of manifest.baseNames) {
    if (!code.baseExports.includes(name)) {
      problems.push({
        file: '前端基类清单 §2',
        rule: 'manifest.base-missing',
        message: `基类「${name}」在 src/base/ 未导出`,
      })
    }
  }

  for (const file of manifest.domainFiles) {
    const basename = file.split('/').pop() ?? file
    if (!code.domainFiles.some((path) => path.endsWith(`/${basename}`))) {
      problems.push({
        file: '前端基类清单 §6',
        rule: 'manifest.domain-missing',
        message: `域基类「${file}」实现缺失`,
      })
    }
  }
  return problems
}
