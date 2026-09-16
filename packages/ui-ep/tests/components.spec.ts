/** ui-ep 首批组件用例：渲染 / 组件根协议（类名与属性）/ 透传 / 状态。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { Divider, GridCol, GridRow, SkeletonBlock, Space } from '../src'

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
