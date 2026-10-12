/** 权限判定与指令用例。 */

import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'

import { vPerm } from '@/directives/perm'
import { canAccess, getPermissionCodes, hasPerm, setPermissionCodes } from '@/utils/perm'

afterEach(() => setPermissionCodes([]))

describe('hasPerm / canAccess', () => {
  it('任一 / 全部 / 取反', () => {
    setPermissionCodes(['a', 'b'])
    expect(getPermissionCodes()).toEqual(['a', 'b'])
    expect(hasPerm('a')).toBe(true)
    expect(hasPerm(['x', 'b'])).toBe(true)
    expect(hasPerm(['a', 'b'], 'all')).toBe(true)
    expect(hasPerm(['a', 'x'], 'all')).toBe(false)
    expect(hasPerm('x', 'not')).toBe(true)
    expect(canAccess('a')).toBe(true)
  })
})

const Host = defineComponent({
  template: "<div><button v-perm=\"'user:read'\">读</button><button v-perm:all=\"['a', 'x']\">全</button></div>",
})

function mountHost() {
  return mount(Host, { global: { directives: { perm: vPerm } } })
}

describe('v-perm 指令', () => {
  it('有权限渲染、无权限移除 DOM', () => {
    setPermissionCodes(['user:read', 'a', 'x'])
    const granted = mountHost()
    expect(granted.findAll('button')).toHaveLength(2)
    granted.unmount()

    setPermissionCodes(['user:read'])
    const partial = mountHost()
    expect(partial.findAll('button')).toHaveLength(1)
    expect(partial.html()).toContain('v-perm')
    partial.unmount()
  })

  it('移除后权限恢复：updated 重新判定并还原元素（restore 命中锚点）', () => {
    setPermissionCodes([])
    const parent = document.createElement('div')
    const el = document.createElement('button')
    parent.appendChild(el)
    const binding = { value: 'user:read' } as never

    vPerm.mounted?.(el, binding)
    expect(parent.querySelector('button')).toBeNull()

    setPermissionCodes(['user:read'])
    vPerm.updated?.(el, binding)
    expect(parent.querySelector('button')).toBe(el)
  })

  it('游离节点（无父节点）重复移除不抛错', () => {
    setPermissionCodes([])
    const detached = document.createElement('button')
    const binding = { value: 'user:read' } as never

    // 无父节点 → `remove` 早退；再次应用同样早退
    expect(() => vPerm.mounted?.(detached, binding)).not.toThrow()
    expect(() => vPerm.updated?.(detached, binding)).not.toThrow()
  })

  it('数组绑定 + `.all` 模式：全部命中才保留', () => {
    const parent = document.createElement('div')
    const el = document.createElement('button')
    parent.appendChild(el)

    setPermissionCodes(['a'])
    vPerm.mounted?.(el, { value: ['a', 'b'], arg: 'all' } as never)
    expect(parent.querySelector('button')).toBeNull()

    setPermissionCodes(['a', 'b'])
    vPerm.updated?.(el, { value: ['a', 'b'], arg: 'all' } as never)
    expect(parent.querySelector('button')).toBe(el)
  })
})
