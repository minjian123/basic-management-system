/** 用户端点封装用例（02_02 / Kiwi 2277 + 02_03 / Kiwi 2248）：服务段寻址、路径 / 方法 / 载荷透传。 */
// kiwi_id: 2277
// kiwi_id: 2248

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  applyUserAssignments,
  createUser,
  deleteUser,
  getUser,
  listUserIdentities,
  listUserRoles,
  listUsers,
  resetUserPassword,
  updateUser,
  updateUserStatus,
} from '@/api/user'

const getMock = vi.fn()
const postMock = vi.fn()
const putMock = vi.fn()
const delMock = vi.fn()

vi.mock('@/api/request', () => ({
  get: (...args: unknown[]) => getMock(...args),
  post: (...args: unknown[]) => postMock(...args),
  put: (...args: unknown[]) => putMock(...args),
  del: (...args: unknown[]) => delMock(...args),
}))

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  putMock.mockReset()
  delMock.mockReset()
})

describe('用户端点封装（02_02 / 02_03）', () => {
  it('列表与详情：platform 服务段只读寻址（含缺省空参数）', async () => {
    await listUsers()
    expect(getMock).toHaveBeenCalledWith('platform', '/users', {})

    await listUsers({ kw: 'dav', status: 'enabled', page: 1, size: 20 })
    expect(getMock).toHaveBeenCalledWith('platform', '/users', { kw: 'dav', status: 'enabled', page: 1, size: 20 })

    await getUser('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/users/1001')
  })

  it('新建 / 修改：POST 新建、PUT 修改（载荷原样透传）', async () => {
    const createBody = {
      username: 'dav',
      name: '戴维',
      status: 'enabled' as const,
      pwd_reset_required: true,
    }
    await createUser(createBody)
    expect(postMock).toHaveBeenCalledWith('platform', '/users', createBody)

    const updateBody = { name: '戴维·李', email: 'dav@example.com', phone: null, version: 2 }
    await updateUser('1001', updateBody)
    expect(putMock).toHaveBeenCalledWith('platform', '/users/1001', updateBody)
  })

  it('启停 / 删除：PUT 状态体（仅 status）与 DELETE', async () => {
    await updateUserStatus('1001', 'disabled')
    expect(putMock).toHaveBeenCalledWith('platform', '/users/1001/status', { status: 'disabled' })

    await deleteUser('1001')
    expect(delMock).toHaveBeenCalledWith('platform', '/users/1001')
  })

  it('重置密码：PUT `/password` 携带请求体', async () => {
    const body = { password: 'Init@2026', pwd_reset_required: false }
    await resetUserPassword('1001', body)
    expect(putMock).toHaveBeenCalledWith('platform', '/users/1001/password', body)
  })

  it('直接角色 / 编排 / SSO 绑定：只读走 GET、编排走 PUT（SSO 归 identity 服务段）', async () => {
    await listUserRoles('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/users/1001/roles')

    const assignments = {
      profile: { name: '戴维', version: 3 },
      role_ids: [2001],
      user_posts: null,
      user_depts: null,
    }
    await applyUserAssignments('1001', assignments)
    expect(putMock).toHaveBeenCalledWith('platform', '/users/1001/assignments', assignments)

    await listUserIdentities('1001')
    expect(getMock).toHaveBeenCalledWith('identity', '/users/1001/identities')
  })
})
