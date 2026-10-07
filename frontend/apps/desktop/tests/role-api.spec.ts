/** 角色端点封装用例（02_03）：服务段寻址（platform）+ 路径 / 方法 / 参数传递。 */
// kiwi_id: 2248

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  assignRoleUsers,
  createRole,
  deleteRole,
  getRole,
  getRoleDataScopes,
  getRoleFields,
  getRolePermissions,
  listRoleUsers,
  listRoles,
  replaceRoleDataScopes,
  replaceRoleFields,
  replaceRolePermissions,
  unassignRoleUser,
  updateRole,
} from '@/api/role'
import { listUsers } from '@/api/user'

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

describe('角色端点封装（02_03）', () => {
  it('角色 CRUD：路径 / 方法 / 载荷透传', async () => {
    await listRoles({ kw: '运维', status: 'enabled', page: 2, size: 20 })
    expect(getMock).toHaveBeenCalledWith('platform', '/roles', { kw: '运维', status: 'enabled', page: 2, size: 20 })

    await getRole('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/roles/1001')

    await createRole({ code: 'ops_admin', name: '运维管理员', status: 'enabled' })
    expect(postMock).toHaveBeenCalledWith('platform', '/roles', {
      code: 'ops_admin',
      name: '运维管理员',
      status: 'enabled',
    })

    await updateRole('1001', { name: '运维负责人', status: 'enabled', version: 2 })
    expect(putMock).toHaveBeenCalledWith('platform', '/roles/1001', {
      name: '运维负责人',
      status: 'enabled',
      version: 2,
    })

    await deleteRole('1001')
    expect(delMock).toHaveBeenCalledWith('platform', '/roles/1001')
  })

  it('用户分配：已分配列表 / 批量分配 / 解绑', async () => {
    await listRoleUsers('1001', { kw: 'ali', page: 1, size: 10 })
    expect(getMock).toHaveBeenCalledWith('platform', '/roles/1001/users', { kw: 'ali', page: 1, size: 10 })

    await assignRoleUsers('1001', { user_ids: ['2001', '2002'] })
    expect(postMock).toHaveBeenCalledWith('platform', '/roles/1001/users', { user_ids: ['2001', '2002'] })

    await unassignRoleUser('1001', '2001')
    expect(delMock).toHaveBeenCalledWith('platform', '/roles/1001/users/2001')
  })

  it('授权 / 字段 / 数据权限：读走 GET、全量覆盖走 PUT', async () => {
    await getRolePermissions('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/roles/1001/permissions')

    await replaceRolePermissions('1001', {
      entries: [{ perm_type: 'menu', target_id: '3001', source_menu_id: '0' }],
    })
    expect(putMock).toHaveBeenCalledWith('platform', '/roles/1001/permissions', {
      entries: [{ perm_type: 'menu', target_id: '3001', source_menu_id: '0' }],
    })

    await getRoleFields('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/roles/1001/fields')
    await replaceRoleFields('1001', {
      entries: [{ form_id: '4001', field_id: '5001', visible: true, editable: false, source_menu_id: '0' }],
    })
    expect(putMock).toHaveBeenCalledWith('platform', '/roles/1001/fields', {
      entries: [{ form_id: '4001', field_id: '5001', visible: true, editable: false, source_menu_id: '0' }],
    })

    await getRoleDataScopes('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/roles/1001/data-permissions')
    await replaceRoleDataScopes('1001', {
      entries: [{ dict_type_id: '6001', policy_type: 'select', config: [{ item_code: 'enabled' }] }],
    })
    expect(putMock).toHaveBeenCalledWith('platform', '/roles/1001/data-permissions', {
      entries: [{ dict_type_id: '6001', policy_type: 'select', config: [{ item_code: 'enabled' }] }],
    })
  })

  it('最小用户只读查询：`/users`（同 platform 服务段）', async () => {
    await listUsers({ kw: 'dav', status: 'enabled', page: 1, size: 20 })
    expect(getMock).toHaveBeenCalledWith('platform', '/users', { kw: 'dav', status: 'enabled', page: 1, size: 20 })
  })
})
