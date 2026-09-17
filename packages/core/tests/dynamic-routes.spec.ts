/** 动态路由能力用例（S6 收口）：菜单树 → 路由构建 / 登记 / 卸载（自旧片段下沉 core）。 */

import { describe, expect, it } from 'vitest'

import { BaseDynamicRoutes, type RouteRecord, type RouteRecordLike } from '../src'

describe('BaseDynamicRoutes（构建）', () => {
  it('buildRoutes：前缀推导 / public 过滤 / 白名单 / 元信息 / 递归子级', () => {
    const routes = new BaseDynamicRoutes()
    const tree = [
      { key: 'sys', title: '系统', path: '/sys', component: 'SysView' },
      { key: 'open', title: '公开', path: '/open', public: true },
      { key: 'skip', title: '白名单', path: '/skip' },
      { key: 'plain', title: '推导', icon: 'star' },
      {
        key: 'parent',
        title: '父级',
        children: [{ key: 'child', title: '子级' }],
      },
    ]
    const records = routes.buildRoutes(tree, { pathPrefix: '/admin', allowedPaths: ['/skip'] })
    expect(records.map((item) => item.name)).toEqual(['sys', 'plain', 'parent'])
    expect(records[0]).toMatchObject({
      name: 'sys',
      path: '/sys',
      component: 'SysView',
      meta: { title: '系统', menuKey: 'sys' },
    })
    expect(records[1]?.path).toBe('/admin/plain')
    expect(records[1]?.meta).toEqual({ title: '推导', icon: 'star', menuKey: 'plain' })
    expect(records[2]?.children?.map((item: RouteRecord) => item.name)).toEqual(['child'])
    expect(records[2]?.children?.[0]?.path).toBe('/admin/child')

    expect(routes.buildRoutes([])).toEqual([])
  })
})

describe('BaseDynamicRoutes（登记 / 卸载）', () => {
  function make(): {
    instance: BaseDynamicRoutes
    registered: string[]
    unregistered: string[]
  } {
    const registered: string[] = []
    const unregistered: string[] = []
    const instance = new BaseDynamicRoutes({
      adapter: {
        register: (items: readonly RouteRecordLike[]) => {
          registered.push(...items.map((item) => item.name))
        },
        unregister: (names: readonly string[]) => {
          unregistered.push(...names)
        },
      },
    })
    return { instance, registered, unregistered }
  }

  it('register 按名去重合并并通知 adapter；hasRoute / routes 联动', () => {
    const { instance, registered } = make()
    expect(instance.register([{ name: 'r1', path: '/r1' }])).toBe(1)
    expect(instance.register([{ name: 'r1', path: '/r1' }, { name: 'r2', path: '/r2' }])).toBe(1)
    expect(registered).toEqual(['r1', 'r2'])
    expect(instance.routes.get().map((item) => item.name)).toEqual(['r1', 'r2'])
    expect(instance.hasRoute('r2')).toBe(true)
    expect(instance.hasRoute('r3')).toBe(false)
  })

  it('unregister 指定 / 全部；reset 清空', () => {
    const { instance, unregistered } = make()
    instance.register([{ name: 'r1', path: '/r1' }, { name: 'r2', path: '/r2' }])
    expect(instance.unregister(['r1'])).toBe(1)
    expect(unregistered).toEqual(['r1'])
    expect(instance.routes.get().map((item) => item.name)).toEqual(['r2'])
    expect(instance.unregister()).toBe(1)
    expect(instance.routes.get()).toEqual([])

    instance.register([{ name: 'r3', path: '/r3' }])
    instance.reset()
    expect(instance.routes.get()).toEqual([])
    expect(instance.hasRoute('r3')).toBe(false)
  })

  it('未注入 adapter：登记不抛错（占位）且 describe 标记 placeholder', () => {
    const instance = new BaseDynamicRoutes()
    expect(() => instance.register([{ name: 'r1', path: '/r1' }])).not.toThrow()
    expect(instance.describe()).toMatchObject({ placeholder: true, registered: 1 })
  })

  it('register 与 unregister 均通知 adapter（顺序：先改状态后通知）', () => {
    const calls: string[] = []
    const instance = new BaseDynamicRoutes({
      adapter: {
        register: () => calls.push('register'),
        unregister: () => calls.push('unregister'),
      },
    })
    instance.register([{ name: 'r1', path: '/r1' }])
    instance.unregister(['r1'])
    expect(calls).toEqual(['register', 'unregister'])
    expect(instance.hasRoute('r1')).toBe(false)
  })
})
