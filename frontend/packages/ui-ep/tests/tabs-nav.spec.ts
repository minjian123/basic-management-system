import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

import { configureConfirm, TabsNav } from '../src'

const confirmMock = vi.fn<(options: unknown) => Promise<boolean>>(async () => true)

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      tabs: {
        refresh: '刷新',
        closeCurrent: '关闭当前',
        closeOthers: '关闭其他',
        closeRight: '关闭右侧',
        closeAll: '关闭全部',
        exceed: '打开的标签过多，已自动关闭最早打开的标签',
      },
    },
  },
})

beforeEach(() => {
  confirmMock.mockReset().mockResolvedValue(true)
  configureConfirm((options) => confirmMock(options))
})

afterEach(() => {
  configureConfirm(undefined)
})

function createTestRouter(): Router {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/user', name: 'user', component: { template: '<div />' } },
      { path: '/role', name: 'role', component: { template: '<div />' } },
      { path: '/log', name: 'log', component: { template: '<div />' } },
    ],
  })
  return router
}

type TabsNavVm = {
  openTab: (tab: Record<string, unknown>) => void
  closeTab: (key: string) => Promise<void>
  activate: (key: string) => void
  cachedNames: string[]
}

function mountTabs(props: Record<string, unknown> = {}, router?: Router) {
  return mount(TabsNav, {
    props,
    global: { plugins: router ? [i18n, router] : [i18n] },
  })
}

function itemByText(wrapper: ReturnType<typeof mountTabs>, text: string) {
  return wrapper.findAll('.bms-tabs-nav-item').find((item) => item.text().includes(text))
}

function menuItemByText(wrapper: ReturnType<typeof mountTabs>, text: string) {
  return wrapper.findAll('.bms-tabs-nav-menu-item').find((item) => item.text().includes(text))
}

describe('多标签导航（Kiwi 731 · 移植）', () => {
  it('固定首签不可关且排首位；打开不重复；cachedNames', async () => {
    const wrapper = mountTabs()
    const vm = wrapper.vm as unknown as TabsNavVm
    vm.openTab({ key: 'user', title: '用户' })
    vm.openTab({ key: 'dashboard', title: '工作台', pinned: true })
    vm.openTab({ key: 'user', title: '用户' })
    await nextTick()

    const items = wrapper.findAll('.bms-tabs-nav-item')
    expect(items).toHaveLength(2)
    expect(items[0]?.text()).toContain('工作台')
    expect(items[0]?.find('.bms-tabs-nav-close').exists()).toBe(false)
    expect(vm.cachedNames).toEqual(['dashboard', 'user'])
  })

  it('点击标签 emit select 且有 router 时 push(path)', async () => {
    const router = createTestRouter()
    const push = vi.spyOn(router, 'push')
    const wrapper = mountTabs({}, router)
    const vm = wrapper.vm as unknown as TabsNavVm
    vm.openTab({ key: 'user', title: '用户', path: '/user' })
    await nextTick()

    await itemByText(wrapper, '用户')?.trigger('click')
    expect(wrapper.emitted('select')?.at(-1)).toEqual(['user'])
    expect(push).toHaveBeenCalledWith('/user')
    push.mockRestore()
  })

  it('关闭激活项激活右邻（无右取左）', async () => {
    const wrapper = mountTabs()
    const vm = wrapper.vm as unknown as TabsNavVm
    vm.openTab({ key: 'dashboard', title: '工作台', pinned: true })
    vm.openTab({ key: 'user', title: '用户' })
    vm.openTab({ key: 'role', title: '角色' })
    vm.activate('user')
    await nextTick()

    await itemByText(wrapper, '用户')?.find('.bms-tabs-nav-close').trigger('click')
    expect(vm.cachedNames).toEqual(['dashboard', 'role'])
    expect(wrapper.find('.bms-tabs-nav-item.is-active').text()).toContain('角色')
  })

  it('右键菜单：关闭其他 / 关闭右侧 / 关闭全部（固定签保留）', async () => {
    const wrapper = mountTabs()
    const vm = wrapper.vm as unknown as TabsNavVm
    vm.openTab({ key: 'dashboard', title: '工作台', pinned: true })
    vm.openTab({ key: 'user', title: '用户' })
    vm.openTab({ key: 'role', title: '角色' })
    vm.openTab({ key: 'log', title: '日志' })
    await nextTick()

    await itemByText(wrapper, '用户')?.trigger('contextmenu')
    expect(wrapper.findAll('.bms-tabs-nav-menu-item')).toHaveLength(5)

    await menuItemByText(wrapper, '关闭其他')?.trigger('click')
    expect(vm.cachedNames).toEqual(['dashboard', 'user'])
    expect(wrapper.emitted('close-others')?.at(-1)).toEqual(['user'])

    await itemByText(wrapper, '用户')?.trigger('contextmenu')
    vm.openTab({ key: 'role', title: '角色' })
    await nextTick()
    await itemByText(wrapper, '用户')?.trigger('contextmenu')
    await menuItemByText(wrapper, '关闭右侧')?.trigger('click')
    expect(vm.cachedNames).toEqual(['dashboard', 'user'])
    expect(wrapper.emitted('close-right')).toBeTruthy()

    await itemByText(wrapper, '用户')?.trigger('contextmenu')
    await menuItemByText(wrapper, '关闭全部')?.trigger('click')
    expect(vm.cachedNames).toEqual(['dashboard'])
    expect(wrapper.emitted('close-all')).toBeTruthy()
  })

  it('非受控 maxOpen 超限：关闭最久未激活并 emit exceed', () => {
    const wrapper = mountTabs({ maxOpen: 2 })
    const vm = wrapper.vm as unknown as TabsNavVm
    vm.openTab({ key: 'user', title: '用户' })
    vm.openTab({ key: 'role', title: '角色' })
    vm.openTab({ key: 'log', title: '日志' })

    expect(vm.cachedNames).toEqual(['role', 'log'])
    expect(wrapper.emitted('exceed')?.at(-1)).toEqual(['user'])
  })

  it('dirty 关闭确认：继续编辑不关，放弃修改关闭', async () => {
    confirmMock.mockResolvedValue(false)
    const wrapper = mountTabs()
    const vm = wrapper.vm as unknown as TabsNavVm
    vm.openTab({ key: 'user', title: '用户', dirty: true })
    await nextTick()

    await itemByText(wrapper, '用户')?.find('.bms-tabs-nav-close').trigger('click')
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(vm.cachedNames).toEqual(['user'])

    confirmMock.mockResolvedValue(true)
    await itemByText(wrapper, '用户')?.find('.bms-tabs-nav-close').trigger('click')
    expect(vm.cachedNames).toEqual([])
    expect(wrapper.emitted('close')?.at(-1)).toEqual(['user'])
  })

  it('transform 刷新 emit；受控模式经 update:* 回写', async () => {
    const controlled = mountTabs({
      tabs: [
        { key: 'dashboard', title: '工作台', pinned: true },
        { key: 'user', title: '用户' },
      ],
      activeKey: 'user',
      transform: true,
    })
    await itemByText(controlled, '用户')?.find('.bms-tabs-nav-refresh').trigger('click')
    expect(controlled.emitted('refresh')?.at(-1)).toEqual(['user'])

    await itemByText(controlled, '用户')?.find('.bms-tabs-nav-close').trigger('click')
    expect(controlled.emitted('update:tabs')?.at(-1)?.[0]).toEqual([
      { key: 'dashboard', title: '工作台', pinned: true },
    ])
    expect(controlled.emitted('update:activeKey')?.at(-1)).toEqual(['dashboard'])

    await itemByText(controlled, '工作台')?.trigger('click')
    expect(controlled.emitted('update:activeKey')?.at(-1)).toEqual(['dashboard'])
  })
})
