/** 动态路由投影用例（S6 收口）：bindings ↔ 核心 `BaseDynamicRoutes`。 */

import { effectScope, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { useDynamicRoutes } from '../src'

const tree = [
  { key: 'sys', title: '系统', path: '/sys' },
  { key: 'plain', title: '推导' },
]

describe('useDynamicRoutes（投影）', () => {
  it('buildRoutes（前缀来自响应式入参）与 register 回调 / 去重 / 响应式', async () => {
    const pathPrefix = ref('/admin')
    const onRegister = vi.fn()
    const onUnregister = vi.fn()
    const scope = effectScope()
    const dynamic = scope.run(() =>
      useDynamicRoutes({ pathPrefix, onRegister, onUnregister }),
    )!

    const records = dynamic.buildRoutes(tree)
    expect(records.map((item) => item.path)).toEqual(['/sys', '/admin/plain'])

    expect(dynamic.register(records)).toBe(2)
    expect(onRegister).toHaveBeenCalledTimes(1)
    expect(dynamic.registered).toEqual(['sys', 'plain'])
    expect(dynamic.hasRoute('sys')).toBe(true)

    expect(dynamic.register(records)).toBe(0)
    expect(onRegister).toHaveBeenCalledTimes(1)

    pathPrefix.value = '/ops'
    expect(dynamic.buildRoutes(tree)[1]?.path).toBe('/ops/plain')

    expect(dynamic.unregister(['sys'])).toBe(1)
    expect(onUnregister).toHaveBeenCalledWith(['sys'])
    expect(dynamic.registered).toEqual(['plain'])

    dynamic.reset()
    await nextTick()
    expect(dynamic.routes).toEqual([])
    scope.stop()
  })

  it('嵌套路由展平登记；作用域释放后订阅取消不抛错', () => {
    const scope = effectScope()
    const dynamic = scope.run(() => useDynamicRoutes())!
    const records = dynamic.buildRoutes([
      { key: 'parent', title: '父', children: [{ key: 'child', title: '子' }] },
    ])
    expect(dynamic.register(records)).toBe(2)
    expect(dynamic.registered).toEqual(['parent', 'child'])
    scope.stop()
    expect(() => dynamic.hasRoute('parent')).not.toThrow()
  })
})
