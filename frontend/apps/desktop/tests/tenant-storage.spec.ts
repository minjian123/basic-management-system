/** 租户编码承载用例（05_02 / Kiwi 2230）：内存态 + 非敏感持久化、存储不可用降级、首次惰性读回。 */
// kiwi_id: 2230

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** 不可用的 `localStorage` 替身（读写均抛错，模拟隐私模式 / 配额）。 */
const BROKEN_STORAGE = {
  getItem: () => {
    throw new Error('storage disabled')
  },
  setItem: () => {
    throw new Error('quota exceeded')
  },
  removeItem: () => {
    throw new Error('storage disabled')
  },
}

/** 每次用例经 `resetModules` 取得全新的模块级内存态（`loaded` / `tenantCode` 单例）。 */
async function freshTenantModule(): Promise<typeof import('@/api/tenant')> {
  vi.resetModules()
  return import('@/api/tenant')
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('租户编码承载（Kiwi 2230）', () => {
  it('首次读取从 localStorage 惰性恢复（`load` 分支）', async () => {
    localStorage.setItem('bms.tenant', 'demo')
    const { getTenantCode } = await freshTenantModule()
    expect(getTenantCode()).toBe('demo')
  })

  it('存储无值时保持内存态为 null', async () => {
    const { getTenantCode } = await freshTenantModule()
    expect(getTenantCode()).toBeNull()
  })

  it('setTenantCode 写入持久化；置 null 移除键', async () => {
    const { getTenantCode, setTenantCode } = await freshTenantModule()

    setTenantCode('demo')
    expect(getTenantCode()).toBe('demo')
    expect(localStorage.getItem('bms.tenant')).toBe('demo')

    setTenantCode(null)
    expect(getTenantCode()).toBeNull()
    expect(localStorage.getItem('bms.tenant')).toBeNull()
  })

  it('读取时存储不可用 → 降级为 null（不抛错）', async () => {
    vi.stubGlobal('localStorage', BROKEN_STORAGE)
    const { getTenantCode } = await freshTenantModule()
    expect(getTenantCode()).toBeNull()
  })

  it('写入时存储不可用 → 仅保留内存态（不阻断登录流程）', async () => {
    vi.stubGlobal('localStorage', BROKEN_STORAGE)
    const { getTenantCode, setTenantCode } = await freshTenantModule()

    expect(() => setTenantCode('demo')).not.toThrow()
    expect(getTenantCode()).toBe('demo')
  })
})
