/** 侧边菜单用例（03_04）。 */

import type { MenuNode } from '@bms/core'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { SideMenu, useSideMenu } from '../src'

const menu: MenuNode[] = [
  { path: '/', title: '工作台' },
  {
    path: '/system',
    title: '系统管理',
    children: [
      { path: '/system/user', title: '用户管理', permission: 'system:user:list' },
      { path: '/system/notice', title: '通知公告', badge: 3 },
    ],
  },
]

const ElMenu = {
  name: 'ElMenu',
  props: ['defaultActive', 'collapse', 'uniqueOpened'],
  emits: ['select'],
  template: '<div class="el-menu"><slot /></div>',
}
const ElSubMenu = {
  name: 'ElSubMenu',
  props: ['index'],
  template: '<div class="el-sub-menu"><slot name="title" /><slot /></div>',
}
const ElMenuItem = {
  name: 'ElMenuItem',
  props: ['index'],
  template: '<div class="el-menu-item" :data-index="index"><slot /></div>',
}
const ElInput = {
  name: 'ElInput',
  props: ['modelValue', 'placeholder'],
  emits: ['update:modelValue', 'input'],
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value); $emit(\'input\', $event.target.value)" />',
}
const ElBadge = {
  name: 'ElBadge',
  props: ['value'],
  template: '<span class="el-badge"><slot /></span>',
}

const stubs = { ElMenu, ElSubMenu, ElMenuItem, ElInput, ElBadge }

describe('useSideMenu', () => {
  it('按权限过滤菜单并计算路由路径', () => {
    const side = useSideMenu({ menu, canAccess: (code) => code === 'system:user:list' })
    expect(side.menu.value.map((node) => node.path)).toEqual(['/', '/system'])
    expect(side.menu.value[1]?.children?.map((node) => node.path)).toEqual(['/system/user', '/system/notice'])
    expect(side.routePaths).toEqual(['/', '/system', '/system/user', '/system/notice'])
  })

  it('关键词过滤与注册 / 卸载（去重保序）', () => {
    const side = useSideMenu({ menu })
    side.setKeyword('通知')
    expect(side.filtered.value.map((node) => node.path)).toEqual(['/system'])
    expect(side.filtered.value[0]?.children?.map((node) => node.path)).toEqual(['/system/notice'])

    expect(side.register()).toEqual(['/', '/system', '/system/user', '/system/notice'])
    side.register()
    expect(side.routes.value).toEqual(['/', '/system', '/system/user', '/system/notice'])

    side.unregister('/system/user')
    expect(side.routes.value).not.toContain('/system/user')
    side.unregister()
    expect(side.routes.value).toEqual([])
  })
})

describe('SideMenu', () => {
  it('渲染多级菜单与徽标，激活路径透传', () => {
    const wrapper = mount(SideMenu, {
      props: { menu, activePath: '/system/user' },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="menu-item-/"]').text()).toContain('工作台')
    expect(wrapper.find('[data-test="menu-sub-/system"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="menu-item-/system/notice"]').text()).toContain('通知公告')
    expect(wrapper.find('.el-badge').exists()).toBe(true)

    const elMenu = wrapper.findComponent(ElMenu)
    expect(elMenu.props('defaultActive')).toBe('/system/user')
    expect(elMenu.props('uniqueOpened')).toBe(true)
  })

  it('搜索过滤菜单并派发 search 事件', async () => {
    const wrapper = mount(SideMenu, { props: { menu, activePath: '/' }, global: { stubs } })
    await wrapper.find('input').setValue('通知')
    expect(wrapper.find('[data-test="menu-item-/"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="menu-item-/system/notice"]').exists()).toBe(true)
    expect(wrapper.emitted('search')?.at(-1)).toEqual(['通知'])
  })

  it('可关闭搜索与徽标，折叠态透传', () => {
    const wrapper = mount(SideMenu, {
      props: { menu, activePath: '/', searchable: false, showBadge: false, collapsed: true },
      global: { stubs },
    })
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.find('.el-badge').exists()).toBe(false)
    expect(wrapper.findComponent(ElMenu).props('collapse')).toBe(true)
  })

  it('菜单选择派发 select', () => {
    const wrapper = mount(SideMenu, { props: { menu, activePath: '/' }, global: { stubs } })
    wrapper.findComponent(ElMenu).vm.$emit('select', '/system/user')
    expect(wrapper.emitted('select')?.[0]).toEqual(['/system/user'])
  })
})
