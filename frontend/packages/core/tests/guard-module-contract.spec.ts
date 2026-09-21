// kiwi_id: 981
/** 契约版本单一来源护栏：core 常量 = `frontend/module-contract.json`（两处漂移即阻断；递增须同步）。 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { MODULE_CONTRACT_VERSION } from '../src'

/** 契约版本单一来源文件（脚本与构建侧消费）。 */
const CONTRACT_FILE = fileURLToPath(new URL('../../../module-contract.json', import.meta.url))

describe('模块契约版本单一来源（Kiwi 981）', () => {
  it('core 常量与 frontend/module-contract.json 一致', () => {
    const source = JSON.parse(readFileSync(CONTRACT_FILE, 'utf8')) as { contractVersion?: unknown }

    expect(Number.isInteger(source.contractVersion)).toBe(true)
    expect(source.contractVersion).toBe(MODULE_CONTRACT_VERSION)
  })
})
