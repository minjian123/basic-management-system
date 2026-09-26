/**
 * 契约生成类型导出面用例（04-1-1 / Kiwi 2191）：命名空间 ↔ 核心服务键一致、生成头齐备。
 */
// kiwi_id: 2191

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { SERVICE_KEYS } from '@bms/core'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const srcDir = resolve(here, '../src')
const index = readFileSync(join(srcDir, 'index.ts'), 'utf8')

describe('契约生成类型导出面（Kiwi 2191）', () => {
  it('index 命名空间集合 == 核心服务键', () => {
    const namespaces = [...index.matchAll(/export type \* as (\w+) from/g)].map((match) => match[1]).sort()
    expect(namespaces).toEqual([...SERVICE_KEYS].sort())
  })

  it('每份服务类型文件存在且带生成头', () => {
    for (const service of SERVICE_KEYS) {
      const path = join(srcDir, `${service}.ts`)
      expect(existsSync(path)).toBe(true)
      expect(readFileSync(path, 'utf8')).toContain('生成，请勿手工修改')
    }
  })
})
