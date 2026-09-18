/** 菜单领域纯函数用例（03_04）。 */

import { describe, expect, it } from 'vitest'

import {
  PLACEHOLDER_MENU,
  filterMenuByKeyword,
  filterMenuByPermission,
  findMenuByPath,
  flattenMenu,
  toRouteNodes,
  type MenuNode,
} from '../src'

const menu: MenuNode[] = [
  { path: '/', title: '工作台' },
  {
    path: '/system',
    title: '系统管理',
    children: [
      { path: '/system/user', title: '用户管理', permission: 'system:user:list' },
      { path: '/system/role', title: '角色管理', permission: 'system:role:list' },
      { path: '/system/notice', title: '通知公告' },
    ],
  },
  { path: '/audit', title: '审计日志', permission: 'audit:log:list' },
]

describe('filterMenuByPermission', () => {
  it('缺省公开项保留，权限项按判定保留 / 剔除', () => {
    const result = filterMenuByPermission(menu, (code) => code === 'system:user:list')
    expect(result.map((node) => node.path)).toEqual(['/', '/system'])
    expect(result[1]?.children?.map((node) => node.path)).toEqual(['/system/user', '/system/notice'])
  })

  it('公开子项保留；子节点全被剔除且自身无权限的空父节点一并剔除', () => {
    const result = filterMenuByPermission(menu, () => false)
    expect(result.map((node) => node.path)).toEqual(['/', '/system'])
    expect(result[1]?.children?.map((node) => node.path)).toEqual(['/system/notice'])

    const tree: MenuNode[] = [
      { path: '/group', title: '分组', children: [{ path: '/group/a', title: 'A', permission: 'group:a' }] },
    ]
    expect(filterMenuByPermission(tree, () => false)).toEqual([])
  })

  it('父节点自身带权限时即使子节点全空仍保留', () => {
    const tree: MenuNode[] = [
      { path: '/group', title: '分组', permission: 'group:view', children: [{ path: '/group/a', title: 'A', permission: 'group:a' }] },
    ]
    const result = filterMenuByPermission(tree, (code) => code === 'group:view')
    expect(result[0]?.path).toBe('/group')
    expect(result[0]?.children).toEqual([])
  })
})

describe('filterMenuByKeyword', () => {
  it('命中节点保留祖先链', () => {
    const result = filterMenuByKeyword(menu, '用户')
    expect(result.map((node) => node.path)).toEqual(['/system'])
    expect(result[0]?.children?.map((node) => node.path)).toEqual(['/system/user'])
  })

  it('父节点命中保留整棵子树', () => {
    const result = filterMenuByKeyword(menu, '系统管理')
    expect(result).toHaveLength(1)
    expect(result[0]?.children).toHaveLength(3)
  })

  it('无命中返回空数组，空关键词返回原树', () => {
    expect(filterMenuByKeyword(menu, '不存在')).toEqual([])
    expect(filterMenuByKeyword(menu, '  ')).toHaveLength(3)
  })
})

describe('flattenMenu / findMenuByPath / toRouteNodes', () => {
  it('先序扁平化含分组节点', () => {
    expect(flattenMenu(menu).map((node) => node.path)).toEqual([
      '/',
      '/system',
      '/system/user',
      '/system/role',
      '/system/notice',
      '/audit',
    ])
  })

  it('按路径查找', () => {
    expect(findMenuByPath(menu, '/system/role')?.title).toBe('角色管理')
    expect(findMenuByPath(menu, '/missing')).toBeUndefined()
  })

  it('转路由节点（名称缺省用路径）', () => {
    const routes = toRouteNodes(menu)
    expect(routes[0]).toMatchObject({ path: '/', name: '/' })
    expect(routes[1]?.children?.[0]).toMatchObject({ path: '/system/user', name: '/system/user' })
  })
})

describe('PLACEHOLDER_MENU', () => {
  it('覆盖多级 / 徽标 / 权限项', () => {
    const flat = flattenMenu(PLACEHOLDER_MENU)
    expect(flat.some((node) => node.badge !== undefined)).toBe(true)
    expect(flat.some((node) => node.permission !== undefined)).toBe(true)
    const dict = findMenuByPath(PLACEHOLDER_MENU, '/system/dict/type')
    expect(dict).toBeDefined()
    expect(flattenMenu(PLACEHOLDER_MENU).length).toBeGreaterThan(6)
  })
})
