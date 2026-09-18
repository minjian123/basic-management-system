/** 护栏：能力登记对账（能力文件 identifier ↔ `CAPABILITY_MANIFEST` ↔《前端基类清单》已交付）。 */

import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { CAPABILITY_MANIFEST } from '../src'

const CAP_DIR = resolve(process.cwd(), 'src/capabilities')
const CHECKLIST = resolve(process.cwd(), '../../../bms文档/前端基类清单.md')

/** 能力文件：identifier → 类名 / 文件名。 */
function scanCapabilities(): { identifier: string; className: string; file: string }[] {
  const result: { identifier: string; className: string; file: string }[] = []
  for (const file of readdirSync(CAP_DIR)) {
    if (!file.endsWith('.ts') || file === 'manifest.ts') {
      continue
    }
    const source = readFileSync(join(CAP_DIR, file), 'utf8')
    const identifier = source.match(/identifier:\s*string\s*=\s*'([a-z-]+)'/)?.[1]
    const className = source.match(/export abstract class (Base[A-Za-z]+)/)?.[1]
    if (identifier !== undefined && className !== undefined) {
      result.push({ identifier, className, file })
    }
  }
  return result
}

/** 《前端基类清单》中状态为「已交付」的基类名。 */
function deliveredBaseNames(): Set<string> {
  const source = readFileSync(CHECKLIST, 'utf8')
  const names = new Set<string>()
  for (const line of source.split('\n')) {
    const match = line.match(/^\|\s*\d+\s*\|\s*`(Base[A-Za-z]+)`\s*\|/)
    if (match !== null && line.includes('已交付')) {
      names.add(match[1] as string)
    }
  }
  return names
}

describe('能力登记对账护栏', () => {
  const capabilities = scanCapabilities()
  const manifestKeys = Object.keys(CAPABILITY_MANIFEST)
  const delivered = deliveredBaseNames()

  it('能力文件数量与 identifier 覆盖', () => {
    expect(capabilities.length).toBeGreaterThan(30)
    expect(delivered.size).toBeGreaterThan(30)
  })

  it('能力文件 identifier 均已登记（漏登记 / 僵尸条目双向为零）', () => {
    const fileIdentifiers = capabilities.map((item) => item.identifier).sort()
    expect(fileIdentifiers, '能力文件 identifier 与登记表不一致').toEqual([...manifestKeys].sort())
  })

  it('每个能力基类均在《前端基类清单》登记为已交付', () => {
    const missing = capabilities.filter((item) => !delivered.has(item.className)).map((item) => `${item.className}(${item.file})`)
    expect(missing, `以下能力基类未在清单登记为已交付：${missing.join(', ')}`).toEqual([])
  })
})
