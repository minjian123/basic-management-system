/** 菜单展开态持久化用例（03_01）：展开 / 收起写入、跨实例恢复、清空。 */
// kiwi_id: 2242

import { beforeEach, describe, expect, it } from 'vitest'

import { MENU_EXPANDED_STORAGE_KEY, useMenuExpanded } from '@/composables/useMenuExpanded'

beforeEach(() => {
  localStorage.clear()
})

describe('useMenuExpanded（03_01）', () => {
  it('展开 / 收起：集合去重并持久化到 localStorage', () => {
    const expanded = useMenuExpanded()
    expanded.toggleOpen('/sys', true)
    expanded.toggleOpen('/sys', true)
    expanded.toggleOpen('/platform', true)

    expect(expanded.expandedKeys.value).toEqual(['/sys', '/platform'])
    expect(JSON.parse(localStorage.getItem(MENU_EXPANDED_STORAGE_KEY) ?? '[]')).toEqual(['/sys', '/platform'])

    expanded.toggleOpen('/sys', false)
    expect(expanded.expandedKeys.value).toEqual(['/platform'])
  })

  it('新建实例按持久化恢复；脏值按空集合处理', () => {
    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, JSON.stringify(['/sys']))
    expect(useMenuExpanded().expandedKeys.value).toEqual(['/sys'])

    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, 'not-json')
    expect(useMenuExpanded().expandedKeys.value).toEqual([])
  })

  it('reset：清空内存态与存储', () => {
    const expanded = useMenuExpanded()
    expanded.toggleOpen('/sys', true)
    expanded.reset()

    expect(expanded.expandedKeys.value).toEqual([])
    expect(JSON.parse(localStorage.getItem(MENU_EXPANDED_STORAGE_KEY) ?? 'null')).toEqual([])
  })

  it('持久化为非数组（JSON 对象 / 字符串）时按空集合处理', () => {
    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, JSON.stringify({ a: 1 }))
    expect(useMenuExpanded().expandedKeys.value).toEqual([])

    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, JSON.stringify('text'))
    expect(useMenuExpanded().expandedKeys.value).toEqual([])
  })

  it('持久化集合剔除非字符串项', () => {
    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, JSON.stringify(['/sys', 1, null, '/platform']))
    expect(useMenuExpanded().expandedKeys.value).toEqual(['/sys', '/platform'])
  })
})
