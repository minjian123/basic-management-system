/** 动态菜单端点封装用例（03_01 / Kiwi 2242）：platform 服务段 `/menus/my` 寻址。 */
// kiwi_id: 2242

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchMyMenus } from '@/api/menu'

const getMock = vi.fn()

vi.mock('@/api/request', () => ({
  get: (...args: unknown[]) => getMock(...args),
}))

beforeEach(() => {
  getMock.mockReset()
})

describe('动态菜单端点封装（03_01）', () => {
  it('取当前用户动态菜单：GET platform `/menus/my`', async () => {
    await fetchMyMenus()
    expect(getMock).toHaveBeenCalledWith('platform', '/menus/my')
  })
})
