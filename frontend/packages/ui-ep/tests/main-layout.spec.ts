/** 主框架布局壳用例（03_05）。 */

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import { MainLayout } from '../src'

const SideMenuStub = {
  name: 'SideMenu',
  props: ['menu', 'activePath', 'collapsed'],
  emits: ['select'],
  template: '<button data-test="menu-stub" @click="$emit(\'select\', \'/system/user\')">菜单</button>',
}

const TabNavBarStub = {
  name: 'TabNavBar',
  props: ['tabs', 'activeKey'],
  emits: ['select', 'close', 'close-others', 'close-right', 'close-all', 'refresh'],
  template: `<div class="tab-nav-bar">
    <button data-test="tabs-select" @click="$emit('select', '/t')">选</button>
    <button data-test="tabs-close" @click="$emit('close', '/t')">关</button>
    <button data-test="tabs-refresh" @click="$emit('refresh', '/t')">刷</button>
  </div>`,
}

const ElDrawerStub = { name: 'ElDrawer', template: '<div class="el-drawer"><slot /></div>' }

const stubs = { SideMenu: SideMenuStub, TabNavBar: TabNavBarStub, ElDrawer: ElDrawerStub }

const baseProps = { menu: [], activePath: '/' }

beforeEach(() => {
  sessionStorage.clear()
})

describe('MainLayout', () => {
  it('渲染侧栏 / 顶栏 / 标签栏 / 内容区插槽', () => {
    const wrapper = mount(MainLayout, {
      props: { ...baseProps, appTitle: 'BMS' },
      slots: { 'header-left': '<span data-test="hl">左</span>', 'header-right': '<span data-test="hr">右</span>', default: '<div data-test="content">内容</div>' },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="menu-stub"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('BMS')
    expect(wrapper.find('[data-test="hl"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="hr"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
    expect(wrapper.findComponent(TabNavBarStub).exists()).toBe(true)
  })

  it('菜单选择与页签事件透传', async () => {
    const wrapper = mount(MainLayout, { props: baseProps, global: { stubs } })
    await wrapper.find('[data-test="menu-stub"]').trigger('click')
    expect(wrapper.emitted('menu-select')?.[0]).toEqual(['/system/user'])

    await wrapper.find('[data-test="tabs-select"]').trigger('click')
    await wrapper.find('[data-test="tabs-close"]').trigger('click')
    await wrapper.find('[data-test="tabs-refresh"]').trigger('click')
    expect(wrapper.emitted('tab-select')?.[0]).toEqual(['/t'])
    expect(wrapper.emitted('tab-close')?.[0]).toEqual(['/t'])
    expect(wrapper.emitted('tab-refresh')?.[0]).toEqual(['/t'])
  })

  it('折叠切换并持久化', async () => {
    const wrapper = mount(MainLayout, { props: { ...baseProps, storageKey: 'layout-test' }, global: { stubs } })
    await wrapper.find('[data-test="layout-toggle"]').trigger('click')
    expect(wrapper.emitted('update:collapsed')?.[0]).toEqual([true])
    expect(sessionStorage.getItem('layout-test')).toContain('"collapsed":true')
  })

  it('可关闭标签栏', () => {
    const wrapper = mount(MainLayout, { props: { ...baseProps, showTabs: false }, global: { stubs } })
    expect(wrapper.findComponent(TabNavBarStub).exists()).toBe(false)
  })

  it('断点变化回传', () => {
    const wrapper = mount(MainLayout, { props: baseProps, global: { stubs } })
    expect(wrapper.emitted('breakpoint-change')?.[0]).toEqual(['wide'])
    expect(wrapper.attributes('data-breakpoint')).toBe('wide')
  })
})
