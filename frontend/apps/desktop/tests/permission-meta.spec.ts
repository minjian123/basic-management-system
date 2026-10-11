// kiwi_id: 2291
/**
 * 权限配置元数据装配用例（02_13）：数据源清单改指 `/data-sources` 并读 `data.items`。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchPermissionMetadata } from '@/api/permissionMeta'

const getMock = vi.fn()

vi.mock('@/api/request', () => ({
  get: (...args: unknown[]) => getMock(...args),
}))

beforeEach(() => {
  getMock.mockReset()
  getMock.mockImplementation((service: string, path: string) => {
    if (path === '/data-sources') {
      return Promise.resolve({
        items: [
          { data_source_key: 'role', name: '角色' },
          { data_source_key: 'user', name: '用户' },
        ],
      })
    }
    return Promise.resolve({ items: [] })
  })
})

describe('权限配置元数据装配（02_13）', () => {
  it('数据源清单改指 /data-sources，读 data.items 映射 dataSourceKeys', async () => {
    const meta = await fetchPermissionMetadata()
    expect(getMock).toHaveBeenCalledWith('platform', '/data-sources')
    expect(getMock).not.toHaveBeenCalledWith('platform', '/dicts')
    expect(meta.dataSourceKeys).toEqual([
      { id: 'role', code: 'role', name: '角色' },
      { id: 'user', code: 'user', name: '用户' },
    ])
  })
})
