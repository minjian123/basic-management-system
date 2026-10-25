/** 护栏：单一落点——第三方库 / 持久化 / 下载 / 浏览器能力不得在组件内直用（须走 `utils/` 与基类投影）。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(process.cwd(), 'src')

/** 组件内禁止直引的第三方库（统一经 utils 单一落点）。 */
const FORBIDDEN_IMPORT = /from\s+['"](dompurify|highlight\.js|@tiptap\/|echarts|@codemirror\/|bpmn-js|socket\.io-client)/

/** 组件内禁止直用的浏览器能力（统一经 utils 单一落点）。 */
const FORBIDDEN_USAGE = [
  /localStorage\s*\./,
  /sessionStorage\s*\./,
  /document\.createElement\s*\(\s*['"]a['"]/,
  /getComputedStyle\s*\(/,
  /new\s+(Intersection|Resize|Mutation)Observer\s*\(/,
  /\bmatchMedia\s*\(/,
  /document\.(exitFullscreen|fullscreenElement|addEventListener|removeEventListener)\b/,
]

/** 去除注释（避免注释中的关键词误判）。 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
}

/**
 * 扫描组件源码中的单一落点违规。
 *
 * @param files 文件清单。
 * @returns 违规项。
 */
export function scanSingleSource(files: { path: string; source: string }[]): string[] {
  const problems: string[] = []
  for (const file of files) {
    const source = stripComments(file.source)
    if (FORBIDDEN_IMPORT.test(source)) {
      const match = source.match(FORBIDDEN_IMPORT)
      problems.push(`${file.path}：组件直引第三方库 ${match?.[0] ?? ''}`)
    }
    for (const pattern of FORBIDDEN_USAGE) {
      if (pattern.test(source)) {
        problems.push(`${file.path}：组件直用浏览器能力 ${pattern}`)
      }
    }
  }
  return problems
}

function walk(dir: string, suffix: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      walk(path, suffix, out)
    } else if (path.endsWith(suffix)) {
      out.push(path)
    }
  }
  return out
}

describe('单一落点护栏', () => {
  it('组件不直引第三方库 / 不直用持久化与浏览器能力', () => {
    const files = walk(join(SRC, 'components'), '.vue').map((path) => ({
      path,
      source: readFileSync(path, 'utf8'),
    }))
    expect(files.length).toBeGreaterThan(10)
    expect(scanSingleSource(files)).toEqual([])
  })

  it('fixture 违规被拦截（第三方 / 持久化 / 下载 / 观察器）', () => {
    const problems = scanSingleSource([
      { path: 'probe.vue', source: "import DOMPurify from 'dompurify'" },
      { path: 'probe2.vue', source: 'const raw = localStorage.getItem("k")' },
      { path: 'probe3.vue', source: 'const a = document.createElement("a"); a.download = "x"' },
      { path: 'probe4.vue', source: 'const o = new ResizeObserver(() => {})' },
    ])
    expect(problems.length).toBeGreaterThanOrEqual(4)
  })
})
