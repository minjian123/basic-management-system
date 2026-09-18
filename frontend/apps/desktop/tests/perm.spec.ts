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
  template: '<div><button v-perm="\'user:read\'">读</button><button v-perm:all="[\'a\', \'x\']">全</button></div>',
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
})
