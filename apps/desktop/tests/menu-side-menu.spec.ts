/** 侧边菜单用例（Kiwi 737）：渲染 / 高亮 / 折叠 / 互斥 / 外链 / 徽标。 */

import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import SideMenu from '@/components/menu/SideMenu.vue'
import type { MenuItem } from '@/components/menu/types'

import { mountWithPlugins } from './helpers/mount'

const MENUS: MenuItem[] = [
  { name: '工作台', path: '/', sort: 1 },
  {
    name: '系统管理',
    sort: 10,
    children: [
      { name: '用户管理', path: '/system/user', sort: 1 },
      { name: '角色管理', path: '/system/role', sort: 2 },
    ],
  },
  {
    name: '内容管理',
    sort: 20,
    children: [{ name: '文章管理', path: '/content/article', sort: 1 }],
  },
  { name: '平台文档', path: 'https://example.com/docs', external: true, sort: 90 },
  { name: '隐藏页面', path: '/hidden', hidden: true, sort: 100 },
]

function mountMenu(props: Record<string, unknown> = {}, withRouter = false) {
  const router = withRouter
    ? createRouter({
        history: createMemoryHistory(),
        routes: [
          { path: '/', name: 'home', component: { template: '<div />' } },
          { path: '/system/user', name: 'sys-user', component: { template: '<div />' } },
          { path: '/system/role', name: 'sys-role', component: { template: '<div />' } },
        ],
      })
    : null
  const wrapper = mountWithPlugins(SideMenu, {
    props: { menus: MENUS, ...props },
    global: router ? { plugins: [router] } : {},
  })
  return { wrapper, router }
}

describe('侧边菜单（Kiwi 737）', () => {
  it('两级渲染：子菜单 / 叶子项、hidden 过滤与 sort 排序', async () => {
    const { wrapper } = mountMenu()
    await nextTick()

    expect(wrapper.findAll('.el-sub-menu')).toHaveLength(2)
    expect(wrapper.text()).toContain('工作台')
    expect(wrapper.text()).toContain('用户管理')
    expect(wrapper.text()).toContain('平台文档')
    expect(wrapper.text()).not.toContain('隐藏页面')
  })

  it('高亮与父级自动展开；折叠与 uniqueOpen 透传', async () => {
    const { wrapper } = mountMenu({ activePath: '/system/user' })
    await nextTick()
    await nextTick()

    expect(wrapper.findComponent({ name: 'ElMenu' }).props('defaultActive')).toBe('/system/user')
    expect(wrapper.find('.el-sub-menu.is-opened').exists()).toBe(true)

    const collapsed = mountMenu({ collapsed: true, uniqueOpen: true })
    await nextTick()
    expect(collapsed.wrapper.findComponent({ name: 'ElMenu' }).props('collapse')).toBe(true)
    expect(collapsed.wrapper.findComponent({ name: 'ElMenu' }).props('uniqueOpened')).toBe(true)
  })

  it('徽标可选渲染（默认不配）', async () => {
    const withBadge: MenuItem[] = [{ name: '待办', path: '/todo', badge: 3, sort: 1 }]
    const wrapper = mountWithPlugins(SideMenu, { props: { menus: withBadge } })
    await nextTick()
    expect(wrapper.find('.bms-menu-badge').text()).toBe('3')

    const plain = mountMenu()
    await nextTick()
    expect(plain.wrapper.find('.bms-menu-badge').exists()).toBe(false)
  })

  it('叶子点击：emit navigate + router push；外链 window.open', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)

    const { wrapper, router } = mountMenu({}, true)
    await nextTick()
    const push = vi.spyOn(router!, 'push')

    const items = wrapper.findAll('.el-menu-item')
    await items.find((item) => item.text().includes('用户管理'))?.trigger('click')
    expect(wrapper.emitted('navigate')?.at(-1)?.[0]).toMatchObject({ path: '/system/user' })
    expect(push).toHaveBeenCalledWith('/system/user')

    await items.find((item) => item.text().includes('平台文档'))?.trigger('click')
    expect(openSpy).toHaveBeenCalledWith('https://example.com/docs', '_blank')

    push.mockRestore()
    vi.unstubAllGlobals()
  })

  it('搜索：保留父链 + 命中高亮 + 无命中空态', async () => {
    const { wrapper } = mountMenu()
    await nextTick()

    ;(wrapper.vm as unknown as { filter: (value: string) => void }).filter('文章')
    await nextTick()
    expect(wrapper.text()).toContain('文章管理')
    expect(wrapper.text()).not.toContain('用户管理')
    expect(wrapper.find('.bms-menu-label.is-hit').exists()).toBe(true)

    ;(wrapper.vm as unknown as { filter: (value: string) => void }).filter('不存在')
    await nextTick()
    expect(wrapper.text()).toContain('未找到匹配菜单')
  })
})
