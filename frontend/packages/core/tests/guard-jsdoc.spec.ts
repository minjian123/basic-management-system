/** 护栏：核心源码注释齐备（模块头 / 导出定义 / 类与接口成员均有 JSDoc）。 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const coreRoot = resolve(import.meta.dirname, '..')

/** 顶层定义（类 / 接口 / 类型 / 常量 / 函数 / 枚举）。 */
const TOP_LEVEL = /^(export\s+)?(abstract\s+)?(class|interface|type|const|function|enum)\b/
/** 类 / 接口成员起始。 */
const MEMBER = /^(static|public|protected|private|readonly|abstract|override|get |set |#|[A-Za-z_])/

interface SourceFile {
  path: string
  source: string
}

function sourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      out.push(...sourceFiles(path))
    } else if (entry.endsWith('.ts')) {
      out.push(path)
    }
  }
  return out
}

/** 找出缺 JSDoc 的顶层定义与类 / 接口成员。 */
export function findMissingJsdoc(files: SourceFile[]): string[] {
  const problems: string[] = []
  const hasJsdoc = (lines: string[], index: number): boolean => {
    let i = index - 1
    // 跳过空行与行注释（如 eslint-disable 指令），要求其上为 JSDoc 块结尾。
    while (i >= 0 && (lines[i].trim() === '' || lines[i].trim().startsWith('//'))) {
      i -= 1
    }
    return i >= 0 && lines[i].trim().endsWith('*/')
  }
  for (const file of files) {
    const lines = file.source.split('\n')
    let depth = 0
    let container = false
    let containerDepth = 0
    for (let i = 0; i < lines.length; i += 1) {
      const text = lines[i]
      const s = text.trim()
      if (/^(export\s+)?(abstract\s+)?(class|interface)\b/.test(s)) {
        container = true
        containerDepth = depth
      }
      const topLevel = /^\S/.test(text) && TOP_LEVEL.test(s) && !s.startsWith('export {') && !s.startsWith('export type {')
      const member = container && depth === containerDepth + 1 && s !== '' && !s.startsWith('//') && !s.startsWith('*') && MEMBER.test(s) && !s.startsWith('constructor')
      if ((topLevel || member) && !hasJsdoc(lines, i)) {
        problems.push(`${file.path}:${i + 1} → ${s.slice(0, 80)}`)
      }
      depth += (text.match(/{/g)?.length ?? 0) - (text.match(/}/g)?.length ?? 0)
      if (container && depth <= containerDepth && /^\}/.test(s)) {
        container = false
      }
    }
  }
  return problems
}

describe('核心注释齐备护栏', () => {
  it('① 源码顶层定义与类 / 接口成员均有 JSDoc', () => {
    const files = sourceFiles(join(coreRoot, 'src')).map((path) => ({
      path,
      source: readFileSync(path, 'utf-8'),
    }))
    expect(files.length).toBeGreaterThan(0)
    expect(findMissingJsdoc(files)).toEqual([])
  })

  it('② fixture 缺注释被拦截（顶层定义 + 类成员）', () => {
    const probe: SourceFile[] = [
      { path: 'probe.ts', source: 'export class Probe {\n  run(): void {}\n}\n' },
    ]
    expect(findMissingJsdoc(probe).length).toBeGreaterThan(0)
  })
})
