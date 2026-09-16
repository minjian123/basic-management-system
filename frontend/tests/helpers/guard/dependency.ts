/**
 * 依赖边界扫描（纯函数，可注入 fixture）：
 * 反向依赖 / UI 库与上层目录 / 片段单向与循环 / 横切库重复实现。
 */

import { importSpecifiers, parseTs, scriptOf, type GuardFile, type GuardProblem } from './ast'

const UI_LIB_PATTERNS = [/^element-plus(\/|$)/, /^@element-plus\//, /^vant(\/|$)/]
const UPPER_LAYER_PATTERNS = [/^@\/views(\/|$)/, /^@\/layouts(\/|$)/]
const CROSS_LIBS = ['axios', 'pinia', 'vue-router', 'vue-i18n']

/** 片段实现文件（`useXxx.ts`，排除域基类组合式 `useXxxBase.ts`） */
function fragmentFileOf(path: string): { dir: string; name: string } | undefined {
  const match = /^src\/components\/base\/([^/]+)\/(use[A-Za-z0-9]+)\.ts$/.exec(path)
  const dir = match?.[1]
  const name = match?.[2]
  if (!dir || !name || /Base$/.test(name)) {
    return undefined
  }
  return { dir, name }
}

/** 相对 import 解析到的片段目录（非片段目录 / 非相对路径返回 `undefined`） */
function resolveRelativeDir(fromPath: string, specifier: string): string | undefined {
  if (!specifier.startsWith('.')) {
    return undefined
  }
  const stack = fromPath.split('/').slice(0, -1)
  for (const part of specifier.split('/')) {
    if (part === '' || part === '.') {
      continue
    }
    if (part === '..') {
      stack.pop()
    } else {
      stack.push(part)
    }
  }
  const match = /^src\/components\/base\/([^/]+)\/use[A-Za-z0-9]+$/.exec(stack.join('/'))
  return match?.[1]
}

/** 片段依赖环检测（DFS） */
function findCycles(depends: Record<string, string[]>): string[][] {
  const cycles: string[][] = []
  const visited = new Set<string>()
  const inStack = new Set<string>()
  const path: string[] = []

  const walk = (key: string): void => {
    if (inStack.has(key)) {
      const start = path.indexOf(key)
      cycles.push([...(start >= 0 ? path.slice(start) : path), key])
      return
    }
    if (visited.has(key)) {
      return
    }
    visited.add(key)
    inStack.add(key)
    path.push(key)
    for (const dep of depends[key] ?? []) {
      if (dep in depends) {
        walk(dep)
      }
    }
    path.pop()
    inStack.delete(key)
  }

  for (const key of Object.keys(depends)) {
    walk(key)
  }
  return cycles
}

/**
 * 扫描依赖边界：
 * R1 `src/base/**` 不 import `src/components/**`；R2 基类层不 import UI 库与上层目录；
 * R3 片段→片段依赖须在 `depends` 登记且无环；R4 不直接 import 横切库（axios / pinia / vue-router / vue-i18n）。
 */
export function scanDependency(files: GuardFile[], fragmentDepends: Record<string, string[]> = {}): GuardProblem[] {
  const problems: GuardProblem[] = []
  for (const file of files) {
    const source = parseTs(scriptOf(file), file.path)
    for (const specifier of importSpecifiers(source)) {
      if (file.path.startsWith('src/base/')) {
        if (
          /^@\/components(\/|$)/.test(specifier) ||
          /(^|\/)\.\.\/components(\/|$)/.test(specifier) ||
          /(^|\/)\.\.\/\.\.\/components(\/|$)/.test(specifier)
        ) {
          problems.push({
            file: file.path,
            rule: 'dependency.reverse-components',
            message: `机制层不得 import 片段 / 组件层：${specifier}`,
          })
        }
      }
      if (file.path.startsWith('src/components/base/')) {
        if (UI_LIB_PATTERNS.some((pattern) => pattern.test(specifier))) {
          problems.push({
            file: file.path,
            rule: 'dependency.ui-lib',
            message: `基类层不得依赖 UI 库（框架无关 / 双端同款）：${specifier}`,
          })
        }
        if (UPPER_LAYER_PATTERNS.some((pattern) => pattern.test(specifier))) {
          problems.push({
            file: file.path,
            rule: 'dependency.upper-layer',
            message: `基类层不得依赖上层目录：${specifier}`,
          })
        }
        if (CROSS_LIBS.some((lib) => specifier === lib || specifier.startsWith(`${lib}/`))) {
          problems.push({
            file: file.path,
            rule: 'dependency.cross-lib',
            message: `横切能力经根系出口 / 片段取得，不得直接 import：${specifier}`,
          })
        }
      }
      const from = fragmentFileOf(file.path)
      const to = resolveRelativeDir(file.path, specifier)
      if (from && to && to !== from.dir) {
        const allowed = fragmentDepends[from.dir]
        if (allowed === undefined) {
          problems.push({
            file: file.path,
            rule: 'dependency.fragment-unregistered',
            message: `片段「${from.dir}」未登记（fragments.ts）却依赖「${to}」`,
          })
        } else if (!allowed.includes(to)) {
          problems.push({
            file: file.path,
            rule: 'dependency.fragment-depends',
            message: `片段「${from.dir}」依赖「${to}」未在 depends 登记（实际 [${allowed.join(', ')}]）`,
          })
        }
      }
    }
  }
  for (const cycle of findCycles(fragmentDepends)) {
    problems.push({
      file: 'src/components/base/fragments.ts',
      rule: 'dependency.fragment-cycle',
      message: `片段依赖存在循环：${cycle.join(' → ')}`,
    })
  }
  return problems
}
