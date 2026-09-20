/** 护栏：令牌消费——组件样式不得硬编码色值（一律 `var(--bms-*)`；令牌定义源与动态计算值豁免）。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(process.cwd(), 'src')

/** 色值字面量（十六进制 / rgb[a] / hsl[a]）。 */
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(/

/** 允许项：令牌定义源（`tokens.scss`）、资源目录、动态计算值（`hsl(${...}` / `rgb(${...}`）。 */
const ALLOWED = [/hsl\(\$\{/, /rgb\(\$\{/]

/** 去注释。 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
}

/**
 * 扫描源码中的硬编码色值。
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
      walk(path, out)
    } else if (path.endsWith('.vue') || path.endsWith('.scss')) {
      out.push(path)
    }
  }
  return out
}

describe('令牌消费护栏', () => {
  it('组件样式无硬编码色值（一律消费令牌）', () => {
    const files = walk(SRC)
      .filter((path) => !path.includes(`${join('src', 'assets')}`))
      .map((path) => ({ path, source: readFileSync(path, 'utf8') }))
    expect(files.length).toBeGreaterThan(10)
    expect(scanColorLiterals(files)).toEqual([])
  })

  it('fixture 违规被拦截（十六进制 / rgba）', () => {
    const problems = scanColorLiterals([
      { path: 'probe.vue', source: '.x { color: #fff; }' },
      { path: 'probe2.vue', source: '.y { background: rgba(0, 0, 0, 0.1); }' },
    ])
    expect(problems.length).toBe(2)
  })

  it('动态计算值与令牌定义源不误判', () => {
    expect(
      scanColorLiterals([
        { path: 'probe.vue', source: 'return `hsl(${hue} 65% 45%)`' },
        { path: 'tokens.scss', source: '.x { color: #fff; }' },
      ]),
    ).toEqual([])
  })
})
