/** 侧边菜单用例：受控渲染 / 搜索与空态 / 导航与外链 / 非受控注入 / 折叠。 */

import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { configureMenuSource, SideMenu, type MenuItem } from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      menu: { searchPlaceholder: '搜索菜单', noMatch: '无匹配菜单', empty: '暂无菜单' },
    },
  },
})

function createTestRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/sys', component: { template: '<div />' } },
      { path: '/orders', component: { template: '<div />' } },
      { path: '/customers', component: { template: '<div />' } },
    ],
  })
}

const menus: MenuItem[] = [
  { name: '系统', path: '/sys', sort: 2 },
  {
    name: '业务',
    sort: 1,
    children: [
      { name: '订单', path: '/orders' },
      { name: '客户', path: '/customers' },
    ],
  },
  { name: '隐藏', path: '/hidden', hidden: true },
]

function mountMenu(props: Record<string, unknown> = {}, router: Router = createTestRouter()) {
  return mount(SideMenu, {
    props: { menus, searchable: true, ...props } as never,
    global: { plugins: [i18n, router] },
  })
}

describe('SideMenu（迁移）', () => {
  it('受控渲染：hidden 过滤、sort 排序、子菜单保留', () => {
    const wrapper = mountMenu()
    const items = wrapper.findAll('.el-menu-item').map((item) => item.text())
    expect(items).toContain('系统')
    expect(items).not.toContain('隐藏')
    expect(wrapper.find('.el-sub-menu__title').text()).toContain('业务')
    expect(items).toContain('订单')
    expect(items).toContain('客户')

    const first = wrapper.find('.el-menu').element.firstElementChild
    expect(first?.className).toContain('el-sub-menu')
  })

  it('搜索：保留父链命中；无匹配出空态；折叠隐藏搜索框', async () => {
    const wrapper = mountMenu()
    ;(wrapper.vm as unknown as { filter: (value: string) => void }).filter('订单')
    await wrapper.vm.$nextTick()
    const items = wrapper.findAll('.el-menu-item').map((item) => item.text())
    expect(items).toContain('订单')
    expect(items).not.toContain('客户')

    ;(wrapper.vm as unknown as { filter: (value: string) => void }).filter('zz')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bms-empty-state').text()).toContain('无匹配菜单')

    const collapsed = mountMenu({ collapsed: true })
    expect(collapsed.find('.bms-side-menu-search').exists()).toBe(false)
  })

  it('导航：select 触发 navigate 与 router.push；外链新开窗口', async () => {
    const openMock = vi.spyOn(window, 'open').mockImplementation(() => null)
    const router = createTestRouter()
    const pushMock = vi.spyOn(router, 'push')
    const wrapper = mountMenu(
      { menus: [...menus, { name: '外链', path: 'https://example.com', external: true }] },
      router,
    )
    const target = wrapper.findAll('.el-menu-item').find((item) => item.text() === '系统')
    await target?.trigger('click')
    expect(wrapper.emitted('navigate')?.[0]?.[0]).toMatchObject({ path: '/sys' })
    expect(pushMock).toHaveBeenCalledWith('/sys')

    const external = wrapper.findAll('.el-menu-item').find((item) => item.text() === '外链')
    await external?.trigger('click')
    expect(openMock).toHaveBeenCalledWith('https://example.com', '_blank')
    expect(wrapper.emitted('navigate')).toHaveLength(1)
    openMock.mockRestore()
  })

  it('非受控：读取注入菜单并回写展开链；未注入为空', async () => {
    const expandByPath = vi.fn()
    const setExpanded = vi.fn()
    configureMenuSource({
      visibleMenus: () => [{ name: '注入项', path: '/inj' }],
      expandedKeys: () => [],
      setExpanded,
      expandByPath,
    })
    const injected = mountMenu({ menus: null, activePath: '/inj' })
    expect(injected.findAll('.el-menu-item').map((item) => item.text())).toContain('注入项')
    expect(expandByPath).toHaveBeenCalledWith('/inj')

    configureMenuSource(undefined)
    const empty = mountMenu({ menus: null })
    expect(empty.findAll('.el-menu-item')).toHaveLength(0)
    expect(empty.find('.bms-empty-state').text()).toContain('暂无菜单')
  })
})

afterEach(() => {
  configureMenuSource(undefined)
})
