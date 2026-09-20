/** 护栏：宿主令牌消费——非令牌定义源的组件 / 样式不得硬编码色值（开发态核对页与令牌源豁免）。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(import.meta.dirname, '..', 'src')

/** 色值字面量。 */
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(/
/** 动态计算值豁免。 */
const ALLOWED = [/hsl\(\$\{/, /rgb\(\$\{/]

/** 去注释。 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
}

/**
 * 扫描硬编码色值。
 *
 * @param files 文件清单。
 * @returns 违规项。
 */
export function scanColorLiterals(files: { path: string; source: string }[]): string[] {
  const problems: string[] = []
  for (const file of files) {
    if (file.path.endsWith('tokens.scss')) {
      continue
    }
    const source = stripComments(file.source)
    const matched = source.match(COLOR_LITERAL)
    if (matched !== null && !ALLOWED.some((pattern) => pattern.test(source))) {
      problems.push(`${file.path}：硬编码色值 ${matched[0]}`)
    }
  }
  return problems
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      if (entry === 'dev') {
        continue
      }
      walk(path, out)
    } else if (path.endsWith('.vue') || path.endsWith('.scss')) {
      out.push(path)
    }
  }
  return out
}

describe('宿主令牌消费护栏', () => {
  it('非令牌源样式无硬编码色值', () => {
    const files = walk(SRC).map((path) => ({ path, source: readFileSync(path, 'utf8') }))
    expect(scanColorLiterals(files)).toEqual([])
  })

  it('fixture 违规被拦截', () => {
    expect(scanColorLiterals([{ path: 'probe.vue', source: '.x { color: #123456; }' }]).length).toBe(1)
  })
})
