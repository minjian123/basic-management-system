/** ui-ep 首批组件用例：渲染 / 组件根协议（类名与属性）/ 透传 / 状态。 */

import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'

import {
  Card,
  Collapse,
  CollapseItem,
  Divider,
  GridCol,
  GridRow,
  LoadingMask,
  SkeletonBlock,
  Space,
  Split,
  Tabs,
} from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: { 'zh-CN': { feedback: { loading: '加载中' } } },
})

describe('ui-ep 布局与反馈组件（首批）', () => {
  it('GridRow / GridCol：组件根协议（nsClass / data-size）与栅格透传', () => {
    const row = mount(GridRow, {
      props: { gutter: 16 },
      slots: { default: '<div class="cell">x</div>' },
      attrs: { 'data-foo': 'bar' },
    })
    expect(row.find('.bms-grid-row').exists()).toBe(true)
    expect(row.find('.bms-grid-row').attributes('data-size')).toBe('default')
    expect(row.find('.bms-grid-row').attributes('data-foo')).toBe('bar')
    expect(row.find('.cell').exists()).toBe(true)

    const col = mount(GridCol, { props: { span: 8 } })
    expect(col.find('.bms-grid-col').exists()).toBe(true)
  })

  it('Space / Divider：组件根协议成立', () => {
    const space = mount(Space, { slots: { default: '<span>a</span><span>b</span>' } })
    expect(space.find('.bms-space').exists()).toBe(true)

    const divider = mount(Divider, { props: { content: '分段' } })
    expect(divider.find('.bms-divider').exists()).toBe(true)
  })

  it('SkeletonBlock：默认骨架行数 / loading=false 渲染内容', () => {
    const skeleton = mount(SkeletonBlock, { props: { variant: 'list', rows: 5 } })
    expect(skeleton.find('.bms-skeleton-block').exists()).toBe(true)
    expect(skeleton.findAll('.bms-skeleton-line')).toHaveLength(5)

    const content = mount(SkeletonBlock, {
      props: { loading: false },
      slots: { default: '<div class="real">内容</div>' },
    })
    expect(content.find('.real').exists()).toBe(true)
  })
})

describe('ui-ep 布局与反馈组件（批 2）', () => {
  it('Card：标题 / 内容渲染', () => {
    const wrapper = mount(Card, {
      props: { title: '标题' },
      slots: { default: '<div class="body">内容</div>' },
    })
    expect(wrapper.find('.bms-card').exists()).toBe(true)
    expect(wrapper.find('.bms-card-title').text()).toBe('标题')
    expect(wrapper.find('.body').exists()).toBe(true)
  })

  it('Collapse / CollapseItem：渲染与面板内容', () => {
    const wrapper = mount(Collapse, {
      props: { modelValue: ['a'] },
      slots: { default: '<div class="item">面板</div>' },
    })
    expect(wrapper.find('.bms-collapse').exists()).toBe(true)
    expect(wrapper.find('.item').exists()).toBe(true)

    const item = mount(CollapseItem, {
      props: { name: 'x', title: '面板一' },
      slots: { default: '<span class="c">内容</span>' },
      global: { plugins: [i18n] },
    })
    expect(item.exists()).toBe(true)
  })

  it('Tabs：渲染与内容区', () => {
    const wrapper = mount(Tabs, {
      props: { modelValue: 'a' },
      slots: { default: '<div class="pane">内容</div>' },
    })
    expect(wrapper.find('.bms-tabs').exists()).toBe(true)
    expect(wrapper.find('.pane').exists()).toBe(true)
  })

  it('Split：渲染与拖拽手柄', () => {
    const wrapper = mount(Split, {
      slots: { first: '<div>左</div>', second: '<div>右</div>' },
    })
    expect(wrapper.find('.bms-split').exists()).toBe(true)
    expect(wrapper.find('.bms-split-splitter').exists()).toBe(true)
  })

  it('LoadingMask：遮罩显示 / 隐藏（delay=0 即时）', () => {
    const shown = mount(LoadingMask, {
      props: { loading: true, delay: 0 },
      global: { plugins: [i18n] },
    })
    expect(shown.find('.bms-loading-mask').exists()).toBe(true)
    expect(shown.find('.bms-loading-mask-overlay').exists()).toBe(true)

    const hidden = mount(LoadingMask, {
      props: { loading: false, delay: 0 },
      global: { plugins: [i18n] },
    })
    expect(hidden.find('.bms-loading-mask').exists()).toBe(true)
    expect(hidden.find('.bms-loading-mask-overlay').exists()).toBe(false)
  })
})
