/** 主框架壳与宿主编排用例（Kiwi 739）：区域 / 折叠 / 菜单路由 / keep-alive。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import AppLayout from '@/components/layout/AppLayout.vue'
import { TabsNav } from '@/components/tabs'
import BasicLayout from '@/layouts/BasicLayout.vue'
import { nameComponent } from '@/router/routeComponent'
import { registerMenuRoutes } from '@/router/menuRoutes'

import { mountWithPlugins } from './helpers/mount'

type MatchMediaStub = {
  matches: boolean
  media: string
  addEventListener: () => void
  removeEventListener: () => void
}

let mediaMatches = false

beforeEach(() => {
  mediaMatches = false
  vi.stubGlobal('matchMedia', (query: string): MatchMediaStub => ({
    matches: mediaMatches,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function makePageComponent(className: string, name: string) {
  return nameComponent(name, {
    name: `${name}-inner`,
    template: `<div class="${className}">page</div>`,
  })
}

function makeHostRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        name: 'layout',
        component: BasicLayout,
        children: [
          { path: '', name: 'home', component: makePageComponent('pg-home', 'home') },
          { path: '/page-a', name: 'page-a', component: makePageComponent('pg-a', 'page-a') },
        ],
      },
      { path: '/403', name: 'error-403', component: { template: '<div />' }, meta: { public: true } },
    ],
  })
}

describe('主框架壳与宿主编排（Kiwi 739）', () => {
  it('AppLayout 区域与插槽；折叠宽度 220 ↔ 64', async () => {
    const wrapper = mountWithPlugins(AppLayout, {
      props: { collapsed: false },
      slots: {
        sidebar: '<div class="side">菜单</div>',
        header: '<div class="head">顶栏</div>',
        tabs: '<div class="tabs">标签</div>',
        default: '<div class="content">内容</div>',
      },
    })
    expect(wrapper.find('.bms-app-layout-sidebar').text()).toContain('菜单')
    expect(wrapper.find('.head').exists()).toBe(true)
    expect(wrapper.find('.tabs').exists()).toBe(true)
    expect(wrapper.find('.content').exists()).toBe(true)
    expect(wrapper.find('.bms-app-layout-sidebar').attributes('style')).toContain('width: 220px')

    await wrapper.setProps({ collapsed: true })
    expect(wrapper.find('.bms-app-layout-sidebar').attributes('style')).toContain('width: 64px')
  })

  it('窄屏：侧栏收进抽屉，toggleSidebar 打开', async () => {
    mediaMatches = true
    const wrapper = mountWithPlugins(AppLayout, {
      props: { collapsed: false },
      slots: { sidebar: '<div class="side">菜单</div>', default: '<div />' },
    })
    await nextTick()
    expect(wrapper.find('.bms-app-layout-sidebar').exists()).toBe(false)

    ;(wrapper.vm as unknown as { toggleSidebar: () => void }).toggleSidebar()
    await nextTick()
    expect(wrapper.findComponent({ name: 'ElDrawer' }).props('modelValue')).toBe(true)
  })

  it('宿主编排：开签 / keep-alive 缓存复用（DOM 复用）/ refresh 重挂载 / 关闭释放', async () => {
    const router = makeHostRouter()
    await router.push('/')
    await router.isReady()

    // 经根 router-view 挂载（路由驱动）：BasicLayout 内部 router-view 才是 children 层级，
    // keep-alive 缓存的即页面组件（直接 mount BasicLayout 会使内部 router-view 成为根级、层级错位）
    const RootView = defineComponent({ template: '<router-view />' })
    const wrapper = mountWithPlugins(RootView, { global: { plugins: [router] } })
    await nextTick()
    await nextTick()

    // 初始开签（home）
    expect(wrapper.text()).toContain('home')
    const homeElement = wrapper.find('.pg-home').element

    await router.push('/page-a')
    await nextTick()
    await nextTick()
    expect(wrapper.find('.pg-a').exists()).toBe(true)
    expect(wrapper.text()).toContain('page-a')
    const pageAElement = wrapper.find('.pg-a').element

    // 切回 home：keep-alive 缓存命中（DOM 元素复用，状态保留）
    await router.push('/')
    await nextTick()
    await nextTick()
    expect(wrapper.find('.pg-home').element).toBe(homeElement)

    // refresh：版本 key 变化 → 重挂载（DOM 元素更新）
    wrapper.findComponent(TabsNav).vm.$emit('refresh', 'home')
    await nextTick()
    await nextTick()
    const refreshedHome = wrapper.find('.pg-home').element
    expect(refreshedHome).not.toBe(homeElement)

    // 关闭 page-a 标签：缓存即时释放 → 再次进入重挂载（新元素）
    const tabsVm = wrapper.findComponent(TabsNav).vm as unknown as {
      closeTab: (key: string) => void
    }
    tabsVm.closeTab('page-a')
    await nextTick()
    await router.push('/page-a')
    await nextTick()
    await nextTick()
    expect(wrapper.find('.pg-a').element).not.toBe(pageAElement)

    // 关闭其他标签不影响 home 缓存复用
    await router.push('/')
    await nextTick()
    await nextTick()
    expect(wrapper.find('.pg-home').element).toBe(refreshedHome)
  })

  it('registerMenuRoutes：菜单 → 路由注册 / 未注册组件回退占位 + 告警', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', name: 'layout', component: { template: '<router-view />' } }],
    })
    const count = registerMenuRoutes(router, [
      { name: '用户管理', path: '/system/user', component: 'PlaceholderView' },
      { name: '目录组', children: [{ name: '未知页', path: '/system/unknown', component: 'NopeView' }] },
    ])
    expect(count).toBe(2)
    expect(router.hasRoute('/system/user')).toBe(true)
    expect(router.hasRoute('/system/unknown')).toBe(true)
    expect(warn).toHaveBeenCalled()

    await router.push('/system/user')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('/system/user')
    warn.mockRestore()
  })
})
