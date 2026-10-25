// kiwi_id: 2235
/** 护栏（XSS）：组件内 `v-html` 必须逐处局部放行 `vue/no-v-html`，且该规则不得被全局关闭。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const ROOT = resolve(process.cwd())
const SRC = join(ROOT, 'src')
const ESLINT_CONFIG = join(ROOT, 'eslint.config.js')

/** `v-html` 使用点。 */
const VHTML = /\bv-html\s*=/g
/** 局部放行注解（`eslint-disable-next-line` 或成对 `eslint-disable`）。 */
const DISABLE = /eslint-disable(?:-next-line)?\s+vue\/no-v-html/g

/**
 * 扫描组件源码中的 `v-html` 放行留痕违规。
 *
 * @param files 文件清单。
 * @returns 违规项。
 */
export function scanVHtmlGuards(files: { path: string; source: string }[]): string[] {
  const problems: string[] = []
  for (const file of files) {
    const usages = file.source.match(VHTML)?.length ?? 0
    if (usages === 0) continue
    const acked = file.source.match(DISABLE)?.length ?? 0
    if (acked < usages) {
      problems.push(
        `${file.path}：${usages} 处 v-html 仅 ${acked} 处局部放行（须逐处 eslint-disable vue/no-v-html 留痕）`,
      )
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

describe('XSS 护栏：v-html 必须经净化并局部放行（Kiwi 2235）', () => {
  it('组件内每个 v-html 均有局部放行注解（禁先全局关闭再裸用）', () => {
    const files = walk(join(SRC, 'components'), '.vue').map((path) => ({
      path,
      source: readFileSync(path, 'utf8'),
    }))
    expect(files.length).toBeGreaterThan(10)
    expect(scanVHtmlGuards(files)).toEqual([])
  })

  it('eslint 未全局关闭 vue/no-v-html，且净化单一入口就位', () => {
    const config = readFileSync(ESLINT_CONFIG, 'utf8')
    expect(config).not.toMatch(/['"]vue\/no-v-html['"]\s*:\s*['"]?(off|0)['"]?/)

    const sanitizer = readFileSync(join(SRC, 'utils', 'sanitizeHtml.ts'), 'utf8')
    expect(sanitizer).toMatch(/export function sanitizeHtml/)
    expect(sanitizer).toMatch(/export function sanitizeSvg/)
  })

  it('fixture 反例被拦截（未放行 / 放行数不足）', () => {
    const problems = scanVHtmlGuards([
      { path: 'probe.vue', source: '<div v-html="content" />' },
      {
        path: 'probe2.vue',
        source: '<!-- eslint-disable-next-line vue/no-v-html -->\n<div v-html="a" />\n<div v-html="b" />',
      },
      {
        path: 'probe3.vue',
        source: '<!-- eslint-disable-next-line vue/no-v-html -->\n<div v-html="a" />',
      },
    ])
    expect(problems.length).toBe(2)
    expect(problems.join('\n')).toContain('probe.vue')
    expect(problems.join('\n')).toContain('probe2.vue')
  })
})
