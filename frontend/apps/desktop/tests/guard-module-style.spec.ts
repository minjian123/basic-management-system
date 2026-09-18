/** 护栏：模块与组件样式作用域约束（scoped / 禁 :global / 禁全局原型修改）。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const ROOT = resolve(process.cwd())
const TARGETS = [join(ROOT, 'src/modules'), resolve(ROOT, '../../packages/ui-ep/src/components')]
const PROTOTYPE_PATTERN = /(Object|Array|String|Number|Boolean)\.prototype/

function walk(dir: string): string[] {
  const result: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      result.push(...walk(path))
    } else if (path.endsWith('.vue') || path.endsWith('.ts')) {
      result.push(path)
    }
  }
  return result
}

describe('样式作用域护栏', () => {
  const files = TARGETS.flatMap((dir) => walk(dir))

  it('存在待检文件', () => {
    expect(files.length).toBeGreaterThan(10)
  })

  it('模块与组件的 <style> 均 scoped 且无 :global', () => {
    const offenders: string[] = []
    for (const file of files) {
      const source = readFileSync(file, 'utf8')
      const blocks = [...source.matchAll(/<style[^>]*>/g)].map((match) => match[0])
      if (blocks.some((tag) => !tag.includes('scoped'))) {
        offenders.push(`${file}（style 未 scoped）`)
      }
      if (source.includes(':global')) {
        offenders.push(`${file}（使用 :global）`)
      }
    }
    expect(offenders, `样式作用域违规：\n${offenders.join('\n')}`).toEqual([])
  })

  it('不改全局原型', () => {
    const offenders = files.filter((file) => PROTOTYPE_PATTERN.test(readFileSync(file, 'utf8')))
    expect(offenders, `全局原型修改：${offenders.join(', ')}`).toEqual([])
  })
})
