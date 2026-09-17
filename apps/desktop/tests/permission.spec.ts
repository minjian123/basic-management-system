/** 权限判定用例（Kiwi 720）：store / hasPerm / canAccess / PermButton（双端同款）。 */

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { configurePermissionChecker, PermButton } from '@bms/ui-ep'
import { i18n } from '@/i18n'
import { usePermissionStore } from '@/stores/permission'
import { canAccess, hasPerm } from '@/utils/perm'

function withStore() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return { pinia, store: usePermissionStore() }
}

describe('权限判定（Kiwi 720）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('⑨ store 占位：无 loader 不请求、空集降级', async () => {
    const { store } = withStore()
    expect(store.isPlaceholder).toBe(true)
    await store.load()
    expect(store.codes).toEqual([])
    expect(store.loaded).toBe(false)
    expect(hasPerm('a')).toBe(false)
  })

  it('⑩ load 装配集合 / 版本 / 菜单；⑪ reset 清空；⑫ Set 与版本', async () => {
    const { store } = withStore()
    const loader = vi.fn().mockResolvedValue({
      codes: ['a', 'b'],
      version: 7,
      menus: [{ key: 'm1', permission: 'a' }],
    })
    store.configureLoader(loader)
    await store.load()
    expect(loader).toHaveBeenCalledTimes(1)
    expect(store.codes).toEqual(['a', 'b'])
    expect(store.permVersion).toBe(7)
    expect(store.menus).toHaveLength(1)
    expect(store.loaded).toBe(true)
    expect(store.permissions.has('a')).toBe(true)
    expect(store.isPlaceholder).toBe(false)

    store.setCodes(['c'])
    expect(store.permVersion).toBe(8)
    expect(store.codes).toEqual(['c'])

    store.reset()
    expect(store.codes).toEqual([])
    expect(store.permVersion).toBe(0)
    expect(store.menus).toEqual([])
    expect(store.loaded).toBe(false)
  })

  it('⑬ hasPerm anyOf / all；⑭ canAccess 各形态', () => {
    const { store } = withStore()
    store.setCodes(['user:create', 'user:update'])

    expect(hasPerm('user:create')).toBe(true)
    expect(hasPerm('user:delete')).toBe(false)
    expect(hasPerm(['user:create', 'user:delete'])).toBe(true)
    expect(hasPerm(['user:create', 'user:delete'], 'all')).toBe(false)
    expect(hasPerm(['user:create', 'user:update'], 'all')).toBe(true)
    expect(hasPerm([])).toBe(true)

    expect(canAccess('user:create')).toBe(true)
    expect(canAccess(['user:create', 'x'])).toBe(true)
    expect(canAccess({ permission: 'user:create' })).toBe(true)
    expect(canAccess({ permission: 'x' })).toBe(false)
    expect(canAccess({ permission: 'x', public: true })).toBe(true)
    expect(canAccess({})).toBe(true)
    expect(canAccess(null)).toBe(true)
    expect(canAccess(undefined)).toBe(true)
  })

  it('⑮ filterRoutes：公开 / 无 permission 保留、递归过滤子级', () => {
    const { store } = withStore()
    store.setCodes(['a'])
    const filtered = store.filterRoutes([
      { key: 'public', public: true },
      { key: 'plain' },
      { key: 'allowed', permission: 'a' },
      { key: 'denied', permission: 'b' },
      {
        key: 'parent',
        permission: 'a',
        children: [
          { key: 'child-ok', permission: 'a' },
          { key: 'child-no', permission: 'b' },
        ],
      },
    ])
    expect(filtered.map((node) => node.key)).toEqual(['public', 'plain', 'allowed', 'parent'])
    expect(filtered[3]?.children?.map((node) => node.key)).toEqual(['child-ok'])
  })

  it('⑯ PermButton fallback=hide / ⑰ disable + 提示 + 点击拦截', async () => {
    const { pinia, store } = withStore()
    // 组件经 ui-ep 权限注入点（未注入=空集）；此处接权限 store 语义
    configurePermissionChecker((codes, mode) =>
      mode === 'all' ? store.hasAll([...codes]) : store.hasAny([...codes]),
    )
    store.setCodes([])

    const hidden = mount(PermButton, {
      props: { perm: 'user:create' },
      slots: { default: '新增' },
      global: { plugins: [pinia, i18n] },
    })
    expect(hidden.find('button').exists()).toBe(false)

    const disabled = mount(PermButton, {
      props: { perm: 'user:create', fallback: 'disable' },
      slots: { default: '新增' },
      global: { plugins: [pinia, i18n] },
    })
    const button = disabled.find('button')
    expect(button.exists()).toBe(true)
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('title')).toBe('没有操作权限')
    await button.trigger('click')
    expect(disabled.emitted('click')).toBeUndefined()

    store.setCodes(['user:create'])
    await disabled.setProps({ perm: 'user:create' })
    expect(disabled.find('button').attributes('disabled')).toBeUndefined()
    await disabled.find('button').trigger('click')
    expect(disabled.emitted('click')).toHaveLength(1)
    configurePermissionChecker(undefined)
  })
})
