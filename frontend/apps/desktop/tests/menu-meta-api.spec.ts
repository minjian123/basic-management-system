/**
 * 权限元数据端点封装用例（03_03）：菜单 / 表单 / 按钮 / 字段 / 业务码 / 动作码 / 权限码 / 图标
 * 的路径、方法、查询参数与载荷透传。
 */
// kiwi_id: 2338

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createAction, deleteAction, listActions, updateAction } from '@/api/action'
import { createBusiness, deleteBusiness, listBusinesses, updateBusiness } from '@/api/business'
import {
  createIcon,
  deleteIcon,
  getIcon,
  listIcons,
  updateIcon,
} from '@/api/icon'
import {
  createButton,
  createField,
  createForm,
  createMenu,
  deleteButton,
  deleteField,
  deleteForm,
  deleteMenu,
  listButtons,
  listFields,
  listForms,
  listMenus,
  updateButton,
  updateField,
  updateForm,
  updateMenu,
} from '@/api/menuMeta'
import {
  createPermission,
  deletePermission,
  generatePermissions,
  listPermissions,
  updatePermission,
} from '@/api/permission'

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

describe('菜单元数据端点封装（03_03）', () => {
  it('菜单 / 表单 / 按钮 / 字段 CRUD：路径与方法', async () => {
    await listMenus()
    expect(getMock).toHaveBeenCalledWith('platform', '/menus')

    const menuPayload = {
      parent_id: '0',
      path: '/sys/menus',
      component: 'sys/menus',
      icon: 'el:menu',
      sort: 10,
      hidden: false,
      status: 'enabled' as const,
      i18n: { 'zh-CN': '菜单管理' },
    }
    await createMenu(menuPayload)
    expect(postMock).toHaveBeenCalledWith('platform', '/menus', menuPayload)
    await updateMenu('1001', menuPayload)
    expect(putMock).toHaveBeenCalledWith('platform', '/menus/1001', menuPayload)
    await deleteMenu('1001')
    expect(delMock).toHaveBeenCalledWith('platform', '/menus/1001')

    await listForms()
    expect(getMock).toHaveBeenCalledWith('platform', '/forms', undefined)
    await listForms('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/forms', { menu_id: '1001' })
    const formPayload = { menu_ids: ['1001'], business_id: '2001', component: '用户表单', status: 'enabled' as const }
    await createForm(formPayload)
    expect(postMock).toHaveBeenCalledWith('platform', '/forms', formPayload)
    await updateForm('3001', formPayload)
    expect(putMock).toHaveBeenCalledWith('platform', '/forms/3001', formPayload)
    await deleteForm('3001')
    expect(delMock).toHaveBeenCalledWith('platform', '/forms/3001')

    await listButtons()
    expect(getMock).toHaveBeenCalledWith('platform', '/buttons', undefined)
    await listButtons('3001')
    expect(getMock).toHaveBeenCalledWith('platform', '/buttons', { form_id: '3001' })
    const buttonPayload = { form_id: '3001', permission_id: '4001', name: '新增', type: 'toolbar' as const, sort: 10, status: 'enabled' as const }
    await createButton(buttonPayload)
    expect(postMock).toHaveBeenCalledWith('platform', '/buttons', buttonPayload)
    await updateButton('5001', buttonPayload)
    expect(putMock).toHaveBeenCalledWith('platform', '/buttons/5001', buttonPayload)
    await deleteButton('5001')
    expect(delMock).toHaveBeenCalledWith('platform', '/buttons/5001')

    await listFields()
    expect(getMock).toHaveBeenCalledWith('platform', '/fields', undefined)
    await listFields('3001')
    expect(getMock).toHaveBeenCalledWith('platform', '/fields', { form_id: '3001' })
    const fieldPayload = {
      form_id: '3001',
      field_key: 'username',
      type: 'string',
      sort: 10,
      status: 'enabled' as const,
      i18n: { 'zh-CN': '用户名' },
    }
    await createField(fieldPayload)
    expect(postMock).toHaveBeenCalledWith('platform', '/fields', fieldPayload)
    await updateField('6001', fieldPayload)
    expect(putMock).toHaveBeenCalledWith('platform', '/fields/6001', fieldPayload)
    await deleteField('6001')
    expect(delMock).toHaveBeenCalledWith('platform', '/fields/6001')
  })
})

describe('业务码 / 动作码端点封装（03_03）', () => {
  it('业务码 CRUD', async () => {
    await listBusinesses()
    expect(getMock).toHaveBeenCalledWith('platform', '/businesses')
    await createBusiness({ code: 'user', status: 'enabled', i18n: { 'zh-CN': '用户' } })
    expect(postMock).toHaveBeenCalledWith('platform', '/businesses', {
      code: 'user',
      status: 'enabled',
      i18n: { 'zh-CN': '用户' },
    })
    await updateBusiness('1', { status: 'disabled', i18n: { 'zh-CN': '用户' } })
    expect(putMock).toHaveBeenCalledWith('platform', '/businesses/1', {
      status: 'disabled',
      i18n: { 'zh-CN': '用户' },
    })
    await deleteBusiness('1')
    expect(delMock).toHaveBeenCalledWith('platform', '/businesses/1')
  })

  it('动作码 CRUD', async () => {
    await listActions()
    expect(getMock).toHaveBeenCalledWith('platform', '/actions')
    await createAction({ code: 'create', status: 'enabled', i18n: { 'zh-CN': '新增' } })
    expect(postMock).toHaveBeenCalledWith('platform', '/actions', {
      code: 'create',
      status: 'enabled',
      i18n: { 'zh-CN': '新增' },
    })
    await updateAction('1', { status: 'enabled', i18n: { 'zh-CN': '新增' } })
    expect(putMock).toHaveBeenCalledWith('platform', '/actions/1', {
      status: 'enabled',
      i18n: { 'zh-CN': '新增' },
    })
    await deleteAction('1')
    expect(delMock).toHaveBeenCalledWith('platform', '/actions/1')
  })
})

describe('权限码端点封装（03_03）', () => {
  it('清单 / 新增 / 补生成 / 更新 / 删除', async () => {
    await listPermissions()
    expect(getMock).toHaveBeenCalledWith('platform', '/permissions', undefined)
    await listPermissions('1')
    expect(getMock).toHaveBeenCalledWith('platform', '/permissions', { business_id: '1' })

    await createPermission({ business_id: '1', action_id: '2', status: 'enabled' })
    expect(postMock).toHaveBeenCalledWith('platform', '/permissions', {
      business_id: '1',
      action_id: '2',
      status: 'enabled',
    })

    await generatePermissions({ business_ids: ['1'], action_ids: [], include_disabled: true })
    expect(postMock).toHaveBeenCalledWith('platform', '/permissions/generate', {
      business_ids: ['1'],
      action_ids: [],
      include_disabled: true,
    })

    await updatePermission('3', { status: 'disabled' })
    expect(putMock).toHaveBeenCalledWith('platform', '/permissions/3', { status: 'disabled' })
    await deletePermission('3')
    expect(delMock).toHaveBeenCalledWith('platform', '/permissions/3')
  })
})

describe('自定义图标端点封装（03_03）', () => {
  it('清单查询参数按需组装（空值不传）', async () => {
    await listIcons()
    expect(getMock).toHaveBeenCalledWith('platform', '/icons', undefined)

    await listIcons({ category: '', status: '', keyword: '' })
    expect(getMock).toHaveBeenLastCalledWith('platform', '/icons', undefined)

    await listIcons({ category: '菜单', status: 'active', keyword: '票据' })
    expect(getMock).toHaveBeenLastCalledWith('platform', '/icons', {
      category: '菜单',
      status: 'active',
      keyword: '票据',
    })
  })

  it('详情 / 新增 / 更新 / 删除', async () => {
    await getIcon('receipt')
    expect(getMock).toHaveBeenCalledWith('platform', '/icons/receipt')

    const createPayload = { code: 'receipt', name: '票据', category: '财务', tags: ['票据'], svg: '<svg />' }
    await createIcon(createPayload)
    expect(postMock).toHaveBeenCalledWith('platform', '/icons', createPayload)

    await updateIcon('receipt', { name: '票据', status: 'disabled' })
    expect(putMock).toHaveBeenCalledWith('platform', '/icons/receipt', { name: '票据', status: 'disabled' })

    await deleteIcon('receipt')
    expect(delMock).toHaveBeenCalledWith('platform', '/icons/receipt')
  })
})
