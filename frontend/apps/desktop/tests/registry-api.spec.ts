// kiwi_id: 2291
/**
 * 登记清单接口封装用例（02_13）：数据源清单（`/data-sources`）与表单标识清单（`/form-keys`）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchDataSourceList, fetchFormKeyList } from '@/api/registry'

const getMock = vi.fn()

vi.mock('@/api/request', () => ({
  get: (...args: unknown[]) => getMock(...args),
}))

beforeEach(() => {
  getMock.mockReset()
  getMock.mockResolvedValue({ items: [] })
})

describe('登记清单接口封装（02_13）', () => {
  it('数据源清单经 platform 服务段取 /data-sources', async () => {
    await fetchDataSourceList()
    expect(getMock).toHaveBeenCalledWith('platform', '/data-sources')
  })

  it('表单标识清单经 platform 服务段取 /form-keys', async () => {
    await fetchFormKeyList()
    expect(getMock).toHaveBeenCalledWith('platform', '/form-keys')
  })
})
