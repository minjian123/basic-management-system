/** 布局余件用例：页面容器 / 应用布局 / 表单框架 / 主从布局 / 主树。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AppLayout,
  configureViewResolver,
  FormFrame,
  MasterDetail,
  MasterTree,
  PageContainer,
  SkeletonBlock,
} from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      layout: { unknownComponent: '未注册组件' },
      tree: { empty: '暂无数据' },
    },
  },
})

function mountIt(component: Parameters<typeof mount>[0], props: Record<string, unknown> = {}, slots: Record<string, string> = {}) {
  return mount(component, {
    props: props as never,
    slots,
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
}

afterEach(() => {
  configureViewResolver(undefined)
})

describe('PageContainer / AppLayout（迁移）', () => {
  it('PageContainer：标题 / 面包屑 / 插槽 / 返回事件', async () => {
    const wrapper = mountIt(
      PageContainer,
      {
        title: '用户管理',
        description: '维护用户资料',
        breadcrumb: [{ label: '首页', path: '/' }, { label: '用户' }],
      },
      { default: '<div class="page-body">正文</div>', extra: '<button class="extra-btn">操作</button>' },
    )
    const root = wrapper.find('.bms-page-container')
    expect(root.text()).toContain('用户管理')
    expect(root.text()).toContain('维护用户资料')
    expect(root.text()).toContain('首页')
    expect(wrapper.find('.page-body').exists()).toBe(true)
    expect(wrapper.find('.extra-btn').exists()).toBe(true)
  })

  it('AppLayout：槽位渲染与侧栏开关', async () => {
    const wrapper = mountIt(
      AppLayout,
      { showSidebar: true, showTabs: true },
      {
        sidebar: '<div class="side-slot">侧栏</div>',
        header: '<div class="header-slot">头部</div>',
        tabs: '<div class="tabs-slot">标签</div>',
        default: '<div class="main-slot">主体</div>',
      },
    )
    expect(wrapper.find('.header-slot').exists()).toBe(true)
    expect(wrapper.find('.main-slot').exists()).toBe(true)
    expect(wrapper.find('.tabs-slot').exists()).toBe(true)

    const hidden = mountIt(AppLayout, { showSidebar: false, showTabs: false }, { default: '<div />' })
    expect(hidden.find('.side-slot').exists()).toBe(false)
    expect(hidden.findAll('.tabs-slot')).toHaveLength(0)
  })
})

describe('FormFrame（迁移）', () => {
  it('视图解析：未注入出空态；注入后渲染视图', async () => {
    const unregistered = mountIt(FormFrame, { listComponent: 'UserList' })
    expect(unregistered.find('.bms-empty-state').text()).toContain('未注册组件')

    configureViewResolver(() => defineComponent({ name: 'FakeView', template: '<div class="fake-view">视图</div>' }))
    const registered = mountIt(FormFrame, { listComponent: 'UserList' })
    expect(registered.find('.fake-view').exists()).toBe(true)
  })
})

describe('MasterDetail（迁移）', () => {
  it('主从槽位与详情空态', () => {
    const withDetail = mountIt(
      MasterDetail,
      { masterTitle: '左侧', hasSelection: true },
      { master: '<div class="master-slot">主区</div>', detail: '<div class="detail-slot">详情</div>' },
    )
    expect(withDetail.find('.master-slot').exists()).toBe(true)
    expect(withDetail.find('.detail-slot').exists()).toBe(true)

    const empty = mountIt(MasterDetail, { hasSelection: false, emptyText: '请选择一项' }, { master: '<div />' })
    expect(empty.find('.bms-empty-state').text()).toContain('请选择一项')
    expect(empty.findAll('.detail-slot')).toHaveLength(0)
  })
})

describe('MasterTree（迁移）', () => {
  it('树渲染 / 懒加载 / 骨架 / 空态', async () => {
    const tree = mountIt(MasterTree, {
      treeData: [{ id: '1', label: '根节点' }],
    })
    expect(tree.text()).toContain('根节点')

    const loadChildren = vi.fn(async () => [{ id: 'x', label: '懒节点' }])
    const lazy = mountIt(MasterTree, { loadMode: 'lazy', loadChildren, treeData: [] })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await lazy.vm.$nextTick()
    expect(loadChildren).toHaveBeenCalledTimes(1)
    expect(lazy.text()).toContain('懒节点')

    const loading = mountIt(MasterTree, { loading: true, treeData: [] })
    expect(loading.findComponent(SkeletonBlock).exists()).toBe(true)

    const empty = mountIt(MasterTree, { treeData: [] })
    expect(empty.find('.bms-empty-state').text()).toContain('暂无数据')
  })
})
