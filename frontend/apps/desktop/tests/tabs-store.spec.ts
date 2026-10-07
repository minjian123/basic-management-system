/** 表单框架页签 store 用例（02_03 角色管理）：列表固定 / 记录增删 / 脏数据拦截 / 激活顺延。 */
// kiwi_id: 2248

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { recordTabKey, useTabsStore } from '@/stores/tabs'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('useTabsStore（02_03）', () => {
  it('reset：仅保留列表页签并激活（列表页签固定不可关）', () => {
    const store = useTabsStore()

    store.reset('list', '角色管理')
    store.open(recordTabKey('1'), '运维管理员')

    store.reset('list', '角色管理')
    expect(store.tabs.map((tab) => tab.key)).toEqual(['list'])
    expect(store.active).toBe('list')
    expect(store.close('list')).toBe(false)
  })

  it('open：新增记录页签并激活；重复打开不新增（仅激活）', () => {
    const store = useTabsStore()
    store.reset('list', '角色管理')

    store.open(recordTabKey('1'), '运维管理员')
    store.open(recordTabKey('2'), '只读角色')
    expect(store.tabs.map((tab) => tab.key)).toEqual(['list', 'record:1', 'record:2'])
    expect(store.active).toBe('record:2')

    store.open(recordTabKey('1'), '运维管理员')
    expect(store.tabs).toHaveLength(3)
    expect(store.active).toBe('record:1')
  })

  it('脏数据拦截：脏页签 close 返回 false（保留），discard 才真正关闭', () => {
    const store = useTabsStore()
    store.reset('list', '角色管理')
    store.open(recordTabKey('1'), '运维管理员')
    store.setDirty(recordTabKey('1'), true)

    expect(store.dirtyKeys).toEqual(['record:1'])
    expect(store.close(recordTabKey('1'))).toBe(false)
    expect(store.tabs).toHaveLength(2)

    expect(store.discard(recordTabKey('1'))).toBe(true)
    expect(store.tabs.map((tab) => tab.key)).toEqual(['list'])
    expect(store.dirtyKeys).toEqual([])
  })

  it('关闭激活页签：激活键顺延到相邻页签；关闭非激活页签不改激活', () => {
    const store = useTabsStore()
    store.reset('list', '角色管理')
    store.open(recordTabKey('1'), '运维管理员')
    store.open(recordTabKey('2'), '只读角色')

    // 关闭非激活页签：激活键保持
    expect(store.close(recordTabKey('1'))).toBe(true)
    expect(store.active).toBe('record:2')

    // 关闭激活页签（末位）：激活键回落到相邻（前一个）页签
    store.open(recordTabKey('3'), '新增角色')
    expect(store.active).toBe('record:3')
    expect(store.close(recordTabKey('3'))).toBe(true)
    expect(store.active).toBe('record:2')
  })

  it('activate：不存在的键忽略；键顺序保持插入序', () => {
    const store = useTabsStore()
    store.reset('list', '角色管理')

    store.activate('record:404')
    expect(store.active).toBe('list')

    store.open(recordTabKey('9'), '九号')
    expect(store.tabs.map((tab) => tab.type)).toEqual(['list', 'record'])
    expect(store.tabs[0]?.closable).toBe(false)
    expect(store.tabs[1]?.closable).toBe(true)
  })
})
