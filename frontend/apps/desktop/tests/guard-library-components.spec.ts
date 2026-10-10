/**
 * 护栏：业务侧组件库件复用 + 宿主样式聚合入口唯一性。
 *
 * **规则一（组件库件复用）**：业务侧 `.vue` 的 `<template>` 内**不得出现裸原生交互元素**
 * （`<input>` / `<button>` / `<select>` / `<textarea>`），一律经组件库件承载——`@bms/ui-ep`
 * 基础控件 / 字段件或 Element Plus 基础件（PC 端 UI 组件库）。**组件库缺件时先补进
 * `@bms/ui-ep`**（并在《组件设计》登记），不在页面自绘。
 *
 * 作用域＝业务侧（各宿主应用与运行时模块的 `src`）；`frontend/packages` 下的组件库自身实现
 * **豁免**——库内以 Element Plus 组件为底座实现库能力，属库实现而非业务自绘。
 *
 * **规则二（样式聚合入口）**：仅 `styles/index.ts` 可引 `tokens.scss`，且其内 Element Plus
 * 样式必须先于令牌（`--el-*` 映射依赖「同优先级后声明覆盖」赢过库默认值）；核对页各有独立
 * HTML 入口，漏引聚合入口会渲染出无底样式的组件库件（2026-10-03 实测发现）。
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

/** 替代件对照（护栏提示用；缺件一律补进 `@bms/ui-ep`）。 */
const REPLACEMENTS: Record<string, string> = {
  input: 'TextInput / PasswordInput / NumberInput / CheckboxInput / RadioInput / FileUploadField（按 type 选件）',
  select: 'SelectInput / OptionField / DictSelectField',
  textarea: 'TextareaInput',
  button: 'Element Plus ElButton（组件库无通用按钮件，按钮统一走 Element Plus）',
}

/** 裸原生交互元素匹配（`<el-input>` / `</button>` / `<el-button>` 不命中）。 */
const NATIVE_ELEMENT = /<(input|button|select|textarea)(\s|\/?>)/g

/** 宿主应用源码根（样式聚合入口落在其中）。 */
const APP_SRC = resolve(import.meta.dirname, '..', 'src')
/** `frontend/` 根。 */
const FRONTEND = resolve(import.meta.dirname, '..', '..', '..')
/** 样式聚合入口（唯一可引令牌的文件）。 */
const STYLE_AGGREGATE = join(APP_SRC, 'styles', 'index.ts')

/**
 * 去 HTML 注释（注释里的示例代码不应命中）。
 *
 * @param source 源码。
 * @returns 去注释后的源码。
 */
function stripComments(source: string): string {
  return source.replace(/<!--[\s\S]*?-->/g, '')
}

/**
 * 取模板段（首个 `<template>` 至最后一个 `</template>`）。
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
 * 扫描模板内的裸原生交互元素。
 *
 * @param files 文件清单（相对路径 + 源码）。
 * @returns 违规描述清单（文件:行号 + 建议替代件）。
 */
export function scanNativeElements(files: { path: string; source: string }[]): string[] {
  const problems: string[] = []
  for (const file of files) {
    const template = stripComments(templateOf(file.source))
    if (template === '') {
      continue
    }
    for (const match of template.matchAll(NATIVE_ELEMENT)) {
      const tag = match[1] ?? ''
      const line = template.slice(0, match.index ?? 0).split('\n').length
      problems.push(`${file.path}:${line}：裸原生 <${tag}> → 改用 ${REPLACEMENTS[tag] ?? '组件库件'}`)
    }
  }
  return problems
}

/**
 * 递归收集指定后缀的文件。
 *
 * @param dir 目录。
 * @param suffixes 后缀清单（如 `.vue`）。
 * @param out 累积结果。
 * @returns 文件绝对路径清单；目录不存在返回空数组。
 */
function walkFiles(dir: string, suffixes: string[], out: string[] = []): string[] {
  if (!existsSync(dir)) {
    return out
  }
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      if (entry === 'node_modules' || entry === 'dist') {
        continue
      }
      walkFiles(path, suffixes, out)
    } else if (suffixes.some((suffix) => path.endsWith(suffix))) {
      out.push(path)
    }
  }
  return out
}

/**
 * 业务侧扫描根：各宿主应用与运行时模块的 `src`。
 *
 * @returns 已存在的源码根清单。
 */
function businessRoots(): string[] {
  const roots: string[] = [APP_SRC]
  for (const group of ['apps', 'modules']) {
    const groupDir = resolve(FRONTEND, group)
    if (!existsSync(groupDir)) {
      continue
    }
    for (const name of readdirSync(groupDir)) {
      const src = join(groupDir, name, 'src')
      if (existsSync(src) && src !== APP_SRC) {
        roots.push(src)
      }
    }
  }
  return roots
}

describe('业务侧组件库件复用护栏', () => {
  it('宿主应用与运行时模块的模板内无裸原生交互元素', () => {
    const paths = businessRoots().flatMap((root) => walkFiles(root, ['.vue']))
    const files = paths.map((path) => ({ path: relative(FRONTEND, path), source: readFileSync(path, 'utf8') }))

    // 扫描面自检：路径写错时本护栏不得静默通过。
    expect(paths.length).toBeGreaterThan(30)
    expect(scanNativeElements(files)).toEqual([])
  })

  it('fixture：裸原生元素被拦截，组件库件与注释放行', () => {
    const flagged = scanNativeElements([
      {
        path: 'probe.vue',
        source:
          '<template><button @click="x">a</button><input v-model="v" /><select /><textarea /></template>',
      },
    ])
    expect(flagged).toHaveLength(4)
    expect(flagged[0]).toContain('裸原生 <button>')

    expect(
      scanNativeElements([
        {
          path: 'probe.vue',
          source:
            '<template><el-button>a</el-button><text-input v-model="v" /><select-input :options="[]" /><!-- <input /> 示例 --></template>',
        },
      ]),
    ).toEqual([])
  })

  it('样式聚合入口唯一：仅 styles/index.ts 引令牌，且 Element Plus 样式先于令牌', () => {
    const offenders = walkFiles(APP_SRC, ['.ts', '.vue'])
      .filter((path) => path !== STYLE_AGGREGATE)
      .filter((path) => /styles\/tokens\.scss|\.\/tokens\.scss/.test(readFileSync(path, 'utf8')))
      .map((path) => relative(FRONTEND, path))

    expect(offenders).toEqual([])

    const aggregate = readFileSync(STYLE_AGGREGATE, 'utf8')
    const elementPlus = aggregate.indexOf("import 'element-plus/dist/index.css'")
    const tokens = aggregate.indexOf("import './tokens.scss'")
    expect(elementPlus).toBeGreaterThan(-1)
    expect(tokens).toBeGreaterThan(elementPlus)
  })
})
