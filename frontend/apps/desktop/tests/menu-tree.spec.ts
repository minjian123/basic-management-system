/**
 * 菜单树纯函数用例（03_03）：扁平化 / 过滤 / 展开策略 / 拖拽调序 → parent_id + sort 计算。
 */
// kiwi_id: 2338

import { describe, expect, it } from 'vitest'

import type { MenuItem } from '@/api/menuMeta'
import {
  cloneMenus,
  countMenus,
  expandableIds,
  expandIdsForKeyword,
  filterMenus,
  findMenu,
  firstLevelExpandableIds,
  flattenMenus,
  isDirectory,
  menuTypeOf,
  nextSort,
  reorderMenus,
  subtreeIds,
  toMenuFlatOptions,
  toMenuTreeOptions,
} from '@/views/system/menu/menuTree'

/**
 * 构造菜单节点。
 *
 * @param overrides 覆盖字段。
 * @returns 菜单节点。
 */
function node(overrides: Partial<MenuItem>): MenuItem {
  return {
    id: '',
    parent_id: '0',
    name: '',
    path: '',
    component: null,
    icon: null,
    sort: 0,
    hidden: false,
    status: 'enabled',
    i18n: {},
    children: [],
    ...overrides,
  }
}

/**
 * 样例树：系统管理（目录）→ 用户 / 角色 / 审计（目录）→ 日志；首页工作台（菜单）。
 *
 * @returns 菜单树。
 */
function sampleTree(): MenuItem[] {
  return [
    node({
      id: 'sys',
      name: '系统管理',
      path: '/sys',
      sort: 10,
      children: [
        node({ id: 'user', parent_id: 'sys', name: '用户管理', path: '/sys/users', component: '用户表单', sort: 10 }),
        node({ id: 'role', parent_id: 'sys', name: '角色管理', path: '/sys/roles', component: '角色表单', sort: 20 }),
        node({
          id: 'audit',
          parent_id: 'sys',
          name: '审计',
          path: '/sys/audit',
          sort: 30,
          children: [
            node({ id: 'log', parent_id: 'audit', name: '审计日志', path: '/sys/audit/log', component: '日志表单', sort: 10 }),
          ],
        }),
      ],
    }),
    node({ id: 'home', name: '首页工作台', path: '/', component: '工作台', sort: 20 }),
  ]
}

describe('菜单树基础（03_03）', () => {
  it('目录判定与类型', () => {
    expect(isDirectory(node({ component: null }))).toBe(true)
    expect(isDirectory(node({ component: '' }))).toBe(true)
    expect(isDirectory(node({ component: 'sys/menus' }))).toBe(false)
    expect(menuTypeOf(node({ component: null }))).toBe('directory')
    expect(menuTypeOf(node({ component: 'x' }))).toBe('menu')
  })

  it('深拷贝：子节点独立', () => {
    const tree = sampleTree()
    const cloned = cloneMenus(tree)
    expect(cloned[0]).not.toBe(tree[0])
    expect(cloned[0]?.children[0]).not.toBe(tree[0]?.children[0])
    expect(cloned[0]?.children[0]?.id).toBe('user')
  })

  it('查找 / 子树 ID / 平铺 / 计数', () => {
    const tree = sampleTree()
    expect(findMenu(tree, 'sys')?.name).toBe('系统管理')
    expect(findMenu(tree, 'log')?.name).toBe('审计日志')
    expect(findMenu(tree, 'ghost')).toBeUndefined()

    expect([...subtreeIds(tree[0] as MenuItem)]).toEqual(['sys', 'user', 'role', 'audit', 'log'])
    expect(flattenMenus(tree).map((item) => item.id)).toEqual(['sys', 'user', 'role', 'audit', 'log', 'home'])
    expect(countMenus(tree)).toBe(6)
  })

  it('展开策略：全部可展开 / 第一层 / 关键字命中路径', () => {
    const tree = sampleTree()
    expect(expandableIds(tree)).toEqual(['sys', 'audit'])
    expect(firstLevelExpandableIds(tree)).toEqual(['sys'])

    expect(expandIdsForKeyword(tree, '')).toEqual([])
    expect(expandIdsForKeyword(tree, '   ')).toEqual([])
    expect(expandIdsForKeyword(tree, '用户')).toEqual(['sys'])
    expect(expandIdsForKeyword(tree, '审计')).toEqual(['sys', 'audit'])
    expect(expandIdsForKeyword(tree, '/sys/audit/log')).toEqual(['sys', 'audit'])
    expect(expandIdsForKeyword(tree, '不存在')).toEqual([])
  })

  it('默认排序值：同级最大值 + 10', () => {
    const tree = sampleTree()
    expect(nextSort(tree, '0')).toBe(30)
    expect(nextSort(tree, 'sys')).toBe(40)
    expect(nextSort(tree, 'ghost')).toBe(10)
  })
})

describe('菜单树过滤（03_03）', () => {
  it('关键字命中保留祖先链（名称 / 路径均命中）', () => {
    const tree = sampleTree()
    expect(filterMenus(tree, { keyword: '用户' }).map((item) => item.id)).toEqual(['sys'])
    expect(filterMenus(tree, { keyword: 'audit/log' })[0]?.children.map((item) => item.id)).toEqual(['audit'])
  })

  it('菜单类型与状态筛选（父级命中时保留其容器位置）', () => {
    const tree = sampleTree()
    const directories = filterMenus(tree, { type: 'directory' })
    expect(directories.map((item) => item.id)).toEqual(['sys'])
    expect(directories[0]?.children.map((item) => item.id)).toEqual(['audit'])

    const menus = filterMenus(tree, { type: 'menu' })
    expect(menus.map((item) => item.id)).toEqual(['sys', 'home'])
    expect(menus[0]?.children.map((item) => item.id)).toEqual(['user', 'role', 'audit'])

    expect(filterMenus(tree, { status: 'disabled' })).toEqual([])
  })

  it('空条件返回完整副本（不修改入参）', () => {
    const tree = sampleTree()
    const filtered = filterMenus(tree, {})
    expect(filtered.map((item) => item.id)).toEqual(['sys', 'home'])
    expect(filtered[0]).not.toBe(tree[0])
  })
})

describe('树拖拽调序（03_03）', () => {
  it('同级并排其后：重排 sort 只提交变化节点', () => {
    const result = reorderMenus(sampleTree(), 'user', 'role', 'after')
    expect(result).toBeDefined()
    expect(result?.tree[0]?.children.map((item) => item.id)).toEqual(['role', 'user', 'audit'])
    expect(result?.moves).toEqual(
      expect.arrayContaining([
        { id: 'role', parent_id: 'sys', sort: 10 },
        { id: 'user', parent_id: 'sys', sort: 20 },
      ]),
    )
  })

  it('拖入目录成为子级（跨父级改 parent_id）', () => {
    const result = reorderMenus(sampleTree(), 'home', 'sys', 'inner')
    expect(result?.tree[0]?.children.map((item) => item.id)).toEqual(['user', 'role', 'audit', 'home'])
    expect(result?.moves).toEqual([{ id: 'home', parent_id: 'sys', sort: 40 }])
  })

  it('拖到根级目标之前（跨父级）', () => {
    const result = reorderMenus(sampleTree(), 'user', 'home', 'before')
    expect(result?.tree.map((item) => item.id)).toEqual(['sys', 'user', 'home'])
    expect(result?.moves).toEqual(
      expect.arrayContaining([
        { id: 'user', parent_id: '0', sort: 20 },
        { id: 'home', parent_id: '0', sort: 30 },
        { id: 'role', parent_id: 'sys', sort: 10 },
        { id: 'audit', parent_id: 'sys', sort: 20 },
      ]),
    )
  })

  it('原位落点无变更（moves 为空）', () => {
    const result = reorderMenus(sampleTree(), 'user', 'role', 'before')
    expect(result?.moves).toEqual([])
  })

  it('非法落点：自身 / 自身子树 / 菜单不可容纳下级 / 节点不存在', () => {
    const tree = sampleTree()
    expect(reorderMenus(tree, 'user', 'user', 'after')).toBeUndefined()
    expect(reorderMenus(tree, 'sys', 'user', 'after')).toBeUndefined()
    expect(reorderMenus(tree, 'user', 'role', 'inner')).toBeUndefined()
    expect(reorderMenus(tree, 'ghost', 'role', 'after')).toBeUndefined()
    expect(reorderMenus(tree, 'user', 'ghost', 'after')).toBeUndefined()
  })

  it('拖入空目录（无子节点）', () => {
    const tree = [node({ id: 'a', sort: 10 }), node({ id: 'dir', sort: 20 })]
    const result = reorderMenus(tree, 'a', 'dir', 'inner')
    expect(result?.tree.map((item) => item.id)).toEqual(['dir'])
    expect(result?.tree[0]?.children.map((item) => item.id)).toEqual(['a'])
    expect(result?.moves).toEqual([
      { id: 'dir', parent_id: '0', sort: 10 },
      { id: 'a', parent_id: 'dir', sort: 10 },
    ])
  })
})

describe('无子节点的叶子节点（03_03）', () => {
  it('空树 / 叶子节点上的查找与重排', () => {
    const bare = [
      node({ id: 'a', name: '甲', path: '/a', sort: 10 }),
      node({ id: 'b', name: '乙', path: '/b', component: 'x', sort: 20 }),
    ]

    expect(cloneMenus(bare)).toHaveLength(2)
    expect(findMenu(bare, 'a')?.id).toBe('a')
    expect(findMenu(bare, 'ghost')).toBeUndefined()
    expect(flattenMenus(bare)).toHaveLength(2)
    expect(countMenus(bare)).toBe(2)
    expect(expandableIds(bare)).toEqual([])
    expect(firstLevelExpandableIds(bare)).toEqual([])
    expect(expandIdsForKeyword(bare, '甲')).toEqual([])
    expect(filterMenus(bare, { keyword: '甲' })).toHaveLength(1)
    expect(nextSort(bare, 'a')).toBe(10)
    expect(reorderMenus(bare, 'a', 'b', 'after')?.tree.map((item) => item.id)).toEqual(['b', 'a'])
    expect(reorderMenus(bare, 'a', 'b', 'inner')).toBeUndefined()
    expect(toMenuTreeOptions(bare, 'a').map((item) => item.id)).toEqual(['0', 'b'])
    expect(toMenuFlatOptions(bare)).toHaveLength(2)

    // 目标父级已不存在（孤儿数据）时容错
    const orphan = [
      node({ id: 'p', parent_id: 'ghost', name: '孤儿', path: '/p', sort: 10 }),
      node({ id: 'q', parent_id: 'ghost', name: '孤儿二', path: '/q', component: 'x', sort: 20 }),
    ]
    expect(reorderMenus(orphan, 'q', 'p', 'after')).toBeDefined()
  })
})

describe('树形 / 平铺选项（03_03）', () => {
  it('父级下拉含根级并排除自身子树', () => {
    const tree = sampleTree()
    const options = toMenuTreeOptions(tree)
    expect(options[0]).toEqual({ id: '0', label: '（根级）' })
    expect(options.map((item) => item.id)).toEqual(['0', 'sys', 'home'])

    const excluded = toMenuTreeOptions(tree, 'sys')
    expect(excluded.map((item) => item.id)).toEqual(['0', 'home'])

    const leafExcluded = toMenuTreeOptions(tree, 'user')
    expect(leafExcluded[1]?.children?.map((item) => item.id)).toEqual(['role', 'audit'])

    expect(toMenuTreeOptions(tree, 'ghost').map((item) => item.id)).toEqual(['0', 'sys', 'home'])
  })

  it('平铺选项含层级路径', () => {
    const options = toMenuFlatOptions(sampleTree())
    expect(options.find((item) => item.id === 'log')?.label).toBe('系统管理 / 审计 / 审计日志')
    expect(options).toHaveLength(6)
  })
})
