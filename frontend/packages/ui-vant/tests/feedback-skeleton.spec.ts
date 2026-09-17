/** 骨架屏用例（Kiwi 753）：形态 / 行数 / 插槽切换。 */

import { describe, expect, it } from 'vitest'

import { SkeletonBlock } from '../src'

import { mountWithPlugins } from './helpers/mount'

describe('骨架屏（Kiwi 753）', () => {
  it('list：van-skeleton 映射与行数', () => {
    const wrapper = mountWithPlugins(SkeletonBlock, { props: { variant: 'list', rows: 4 } })
    expect(wrapper.find('.bms-skeleton-block').exists()).toBe(true)
    expect(wrapper.find('.van-skeleton').exists()).toBe(true)
    expect(wrapper.find('.bms-skeleton--list').exists()).toBe(true)
    expect(wrapper.findAll('.bms-skeleton-line')).toHaveLength(4)
  })

  it('table：表头 + rows 行；form：label + 控件块；card：封面 + 标题 + 段落', () => {
    const table = mountWithPlugins(SkeletonBlock, { props: { variant: 'table', rows: 3 } })
    expect(table.find('.bms-skeleton--table').exists()).toBe(true)
    expect(table.findAll('.bms-skeleton-row')).toHaveLength(4)
    expect(table.find('.bms-skeleton-row.is-head').exists()).toBe(true)
    expect(table.findAll('.bms-skeleton-cell')).toHaveLength(16)

    const form = mountWithPlugins(SkeletonBlock, { props: { variant: 'form', rows: 2 } })
    expect(form.find('.bms-skeleton--form').exists()).toBe(true)
    expect(form.findAll('.bms-skeleton-field')).toHaveLength(2)
    expect(form.findAll('.bms-skeleton-label')).toHaveLength(2)
    expect(form.findAll('.bms-skeleton-control')).toHaveLength(2)

    const card = mountWithPlugins(SkeletonBlock, { props: { variant: 'card' } })
    expect(card.find('.bms-skeleton--card').exists()).toBe(true)
    expect(card.find('.bms-skeleton-cover').exists()).toBe(true)
    expect(card.find('.bms-skeleton-line.is-title').exists()).toBe(true)
  })

  it('animated 关闭 / 开启与 loading=false 渲染插槽', () => {
    const animated = mountWithPlugins(SkeletonBlock, { props: { variant: 'table', animated: true } })
    expect(animated.find('.bms-skeleton.is-animated').exists()).toBe(true)

    const still = mountWithPlugins(SkeletonBlock, { props: { variant: 'table', animated: false } })
    expect(still.find('.bms-skeleton.is-animated').exists()).toBe(false)

    const loaded = mountWithPlugins(SkeletonBlock, {
      props: { loading: false },
      slots: { default: '<div class="content">内容</div>' },
    })
    expect(loaded.find('.content').exists()).toBe(true)
    expect(loaded.find('.bms-skeleton').exists()).toBe(false)
  })
})
