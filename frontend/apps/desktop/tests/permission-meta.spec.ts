// kiwi_id: 2291
/**
 * 权限配置元数据装配用例（02_13）：菜单 / 表单 / 字段 / 按钮 / 权限码映射，
 * 数据源清单改指 `/data-sources` 并读 `data.items`（含脏项剔除）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchPermissionMetadata } from '@/api/permissionMeta'

const getMock = vi.fn()

vi.mock('@/api/request', () => ({
  get: (...args: unknown[]) => getMock(...args),
}))

/** 各端点桩数据（菜单树嵌套 / 表单 / 字段 / 按钮 / 权限码 / 数据源）。 */
const RESPONSES: Record<string, unknown> = {
  '/menus': {
    items: [
      {
        id: 10,
        name: '系统管理',
        icon: 'setting',
        children: [{ id: 11, name: '用户管理', icon: null, children: null }],
      },
    ],
  },
  '/forms': { items: [{ id: 100, component: 'sys/user', business_id: 1, menu_ids: [11] }] },
  '/fields': { items: [{ id: 200, form_id: 100, name: '登录账号' }] },
  '/buttons': {
    items: [
      { form_id: 100, permission_id: 300 },
      { form_id: 100, permission_id: 300 },
    ],
  },
  '/permissions': { items: [{ id: 300, code: 'user:create' }] },
  '/data-sources': {
    items: [
      { data_source_key: 'role', name: '角色' },
      null,
      { data_source_key: '', name: '空键' },
      { data_source_key: 'user' },
    ],
  },
}

beforeEach(() => {
  getMock.mockReset()
  getMock.mockImplementation((_service: string, path: string) => Promise.resolve(RESPONSES[path] ?? { items: [] }))
})

describe('权限配置元数据装配（02_13）', () => {
  it('数据源清单改指 /data-sources，读 data.items 映射并剔除脏项', async () => {
    const meta = await fetchPermissionMetadata()
    expect(getMock).toHaveBeenCalledWith('platform', '/data-sources')
    expect(getMock).not.toHaveBeenCalledWith('platform', '/dicts')
    expect(meta.dataSourceKeys).toEqual([
      { id: 'role', code: 'role', name: '角色' },
      { id: 'user', code: 'user', name: 'user' },
    ])
  })

  it('菜单树递归映射、表单 / 字段 / 动作与按钮索引装配', async () => {
    const meta = await fetchPermissionMetadata()
    expect(meta.menus).toEqual([
      {
        id: '10',
        name: '系统管理',
        icon: 'setting',
        children: [{ id: '11', name: '用户管理', icon: undefined, children: [] }],
      },
    ])
    expect(meta.forms).toEqual([{ id: '100', name: 'sys/user', menuIds: ['11'] }])
    expect(meta.fields).toEqual([{ id: '200', name: '登录账号' }])
    expect(meta.actions).toEqual([{ id: '300', name: 'user:create' }])
    // 按钮同表单同权限去重
    expect(meta.formActions).toEqual({ 100: ['300'] })
    expect(meta.formFields).toEqual({ 100: ['200'] })
    expect(meta.extensions).toEqual([])
  })

  it('缺省项（无表单 / 无字段 / 无按钮 / 无权限码）回落空集合', async () => {
    getMock.mockImplementation((_service: string, path: string) =>
      Promise.resolve(path === '/data-sources' ? { items: [] } : {}),
    )
    const meta = await fetchPermissionMetadata()
    expect(meta.menus).toEqual([])
    expect(meta.forms).toEqual([])
    expect(meta.formActions).toEqual({})
    expect(meta.formFields).toEqual({})
    expect(meta.actions).toEqual([])
    expect(meta.dataSourceKeys).toEqual([])
  })

  it('表单缺 component 时回落「表单 {id}」', async () => {
    getMock.mockImplementation((_service: string, path: string) =>
      Promise.resolve(path === '/forms' ? { items: [{ id: 101, component: null }] } : { items: [] }),
    )
    const meta = await fetchPermissionMetadata()
    expect(meta.forms).toEqual([{ id: '101', name: '表单 101', menuIds: [] }])
  })

  it('数据源清单缺 items 时回落空集合', async () => {
    getMock.mockImplementation((_service: string, path: string) =>
      Promise.resolve(path === '/data-sources' ? {} : { items: [] }),
    )
    const meta = await fetchPermissionMetadata()
    expect(meta.dataSourceKeys).toEqual([])
  })
})
