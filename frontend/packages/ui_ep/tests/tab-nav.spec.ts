/** 多标签导航用例（03_03_01）。 */

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import { DualTabs, TabNavBar, useConfirm, useTabNav, type TabNavItem } from '../src'

function tab(key: string, extra: Partial<TabNavItem> = {}): TabNavItem {
  return { key, title: key.toUpperCase(), path: key, ...extra }
}

beforeEach(() => {
  sessionStorage.clear()
})

describe('useTabNav 基本行为', () => {
  it('打开 / 去重 / 激活与 keep-alive 名单', () => {
    const nav = useTabNav()
    nav.open(tab('/home', { closable: false, keepAlive: true }))
    nav.open(tab('/list', { keepAlive: true }))
    nav.open(tab('/detail', { keepAlive: false }))

    expect(nav.tabs.value).toHaveLength(3)
    expect(nav.activeKey.value).toBe('/detail')
    expect(nav.cachedKeys.value).toEqual(['/home', '/list'])

    nav.open(tab('/home'))
    expect(nav.tabs.value).toHaveLength(3)
    expect(nav.activeKey.value).toBe('/home')
  })

  it('关闭当前页签激活右邻（无则左邻）', async () => {
    const right = useTabNav()
    right.open(tab('/a'))
    right.open(tab('/b'))
    right.open(tab('/c'))
    expect(await right.close('/b')).toBe(true)
    expect(right.activeKey.value).toBe('/c')

    const left = useTabNav()
    left.open(tab('/a'))
    left.open(tab('/b'))
    expect(await left.close('/b')).toBe(true)
    expect(left.activeKey.value).toBe('/a')
  })

  it('固定页签拒绝关闭', async () => {
    const nav = useTabNav()
    nav.open(tab('/home', { closable: false }))
    expect(await nav.close('/home')).toBe(false)
    expect(nav.tabs.value).toHaveLength(1)
  })

  it('脏数据关闭经二次确认', async () => {
    const confirm = useConfirm()
    const nav = useTabNav()
    nav.open(tab('/a'))
    nav.markDirty('/a')

    const pending = nav.close('/a')
    confirm.resolveConfirm(true)
    expect(await pending).toBe(true)
    expect(nav.tabs.value).toHaveLength(0)
  })

  it('关闭其他 / 右侧 / 全部保留固定页签', async () => {
    const nav = useTabNav()
    nav.open(tab('/home', { closable: false }))
    nav.open(tab('/a'))
    nav.open(tab('/b'))
    nav.open(tab('/c'))

    await nav.closeOthers('/a')
    expect(nav.tabs.value.map((item) => item.key)).toEqual(['/home', '/a'])

    nav.open(tab('/b'))
    await nav.closeRight('/a')
    expect(nav.tabs.value.map((item) => item.key)).toEqual(['/home', '/a'])

    nav.open(tab('/b'))
    await nav.closeAll()
    expect(nav.tabs.value.map((item) => item.key)).toEqual(['/home'])
  })

  it('刷新临时移除缓存键后恢复', async () => {
    const nav = useTabNav()
    nav.open(tab('/a', { keepAlive: true }))
    nav.refresh('/a')
    expect(nav.refreshing.value).toBe('/a')
    expect(nav.cachedKeys.value).toEqual([])
    await Promise.resolve()
    expect(nav.cachedKeys.value).toEqual(['/a'])
  })
})

describe('useTabNav 持久化', () => {
  it('写入并在新实例恢复', () => {
    const first = useTabNav({ storageKey: 'tabnav-test' })
    first.open(tab('/a', { keepAlive: true }))
    first.open(tab('/b'))

    const restored = useTabNav({ storageKey: 'tabnav-test' })
    expect(restored.tabs.value.map((item) => item.key)).toEqual(['/a', '/b'])
    expect(restored.activeKey.value).toBe('/b')
    expect(restored.cachedKeys.value).toEqual(['/a'])
  })

  it('脏数据不进入持久化', () => {
    const nav = useTabNav({ storageKey: 'tabnav-dirty' })
    nav.open(tab('/a'))
    nav.markDirty('/a')
    const raw = sessionStorage.getItem('tabnav-dirty') ?? ''
    expect(raw).not.toContain('"dirty":true')
  })
})

describe('TabNavBar', () => {
  const tabs = [tab('/a'), tab('/b'), tab('/c')]

  it('选择与关闭派发事件', async () => {
    const wrapper = mount(TabNavBar, { props: { tabs, activeKey: '/a' } })
    await wrapper.find('[data-test="tab-/b"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['/b'])

    await wrapper.find('[data-test="tab-close-/b"]').trigger('click')
    expect(wrapper.emitted('close')?.[0]).toEqual(['/b'])
  })

  it('右键菜单派发关闭其他 / 刷新 / 关闭全部', async () => {
    const wrapper = mount(TabNavBar, { props: { tabs, activeKey: '/a' } })
    await wrapper.find('[data-test="tab-/b"]').trigger('contextmenu')
    expect(wrapper.find('[data-test="tab-context"]').exists()).toBe(true)

    await wrapper.find('[data-test="tab-ctx-close-others"]').trigger('click')
    expect(wrapper.emitted('close-others')?.[0]).toEqual(['/b'])

    await wrapper.find('[data-test="tab-/b"]').trigger('contextmenu')
    await wrapper.find('[data-test="tab-ctx-refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')?.[0]).toEqual(['/b'])

    await wrapper.find('[data-test="tab-/b"]').trigger('contextmenu')
    await wrapper.find('[data-test="tab-ctx-close-all"]').trigger('click')
    expect(wrapper.emitted('close-all')).toHaveLength(1)
  })

  it('固定页签禁用关闭类菜单项', async () => {
    const wrapper = mount(TabNavBar, {
      props: { tabs: [tab('/home', { closable: false })], activeKey: '/home' },
    })
    await wrapper.find('[data-test="tab-/home"]').trigger('contextmenu')
    expect(wrapper.find('[data-test="tab-ctx-close"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="tab-ctx-refresh"]').attributes('disabled')).toBeUndefined()
  })

  it('超出折叠进更多', async () => {
    const wrapper = mount(TabNavBar, { props: { tabs, activeKey: '/a', maxVisible: 2 } })
    expect(wrapper.find('[data-test="tab-/c"]').exists()).toBe(false)
    await wrapper.find('[data-test="tab-more"]').trigger('click')
    await wrapper.find('[data-test="tab-more-/c"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['/c'])
  })
})

describe('DualTabs', () => {
  it('上下层各自派发选择', async () => {
    const wrapper = mount(DualTabs, {
      props: {
        primary: [tab('/p1'), tab('/p2')],
        primaryKey: '/p1',
        secondary: [tab('/s1')],
        secondaryKey: '/s1',
      },
    })
    await wrapper.find('[data-test="tab-/p2"]').trigger('click')
    await wrapper.find('[data-test="tab-/s1"]').trigger('click')
    expect(wrapper.emitted('update:primaryKey')?.[0]).toEqual(['/p2'])
    expect(wrapper.emitted('update:secondaryKey')?.[0]).toEqual(['/s1'])
    expect(wrapper.emitted('select')?.map((args) => args[0])).toEqual(['primary', 'secondary'])
  })
})
