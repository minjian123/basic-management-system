/** 骨架屏用例（Kiwi 728）：形态 / 行数 / 插槽切换。 */

import { describe, expect, it } from 'vitest'

import SkeletonBlock from '@/components/feedback/SkeletonBlock.vue'

import { mountWithPlugins } from './helpers/mount'

function mountSkeleton(props: Record<string, unknown> = {}) {
  return mountWithPlugins(SkeletonBlock, { props })
}

describe('骨架屏（Kiwi 728）', () => {
  it('variant 四形态结构类', () => {
    expect(mountSkeleton({ variant: 'list' }).find('.bms-skeleton--list').exists()).toBe(true)
    expect(mountSkeleton({ variant: 'table' }).find('.bms-skeleton--table').exists()).toBe(true)
    expect(mountSkeleton({ variant: 'form' }).find('.bms-skeleton--form').exists()).toBe(true)
    expect(mountSkeleton({ variant: 'card' }).find('.bms-skeleton--card').exists()).toBe(true)
  })

  it('rows 控制行数（list / table）', () => {
    const list = mountSkeleton({ variant: 'list', rows: 3 })
    expect(list.findAll('.bms-skeleton-line')).toHaveLength(3)

    const table = mountSkeleton({ variant: 'table', rows: 2 })
    // 表头 1 行 + 数据 2 行
    expect(table.findAll('.bms-skeleton-row')).toHaveLength(3)
  })

  it('card / form 结构块齐备', () => {
    const card = mountSkeleton({ variant: 'card' })
    expect(card.find('.bms-skeleton-cover').exists()).toBe(true)
    expect(card.findAll('.bms-skeleton-line').length).toBeGreaterThanOrEqual(3)

    const form = mountSkeleton({ variant: 'form', rows: 2 })
    expect(form.findAll('.bms-skeleton-field')).toHaveLength(2)
    expect(form.find('.bms-skeleton-label').exists()).toBe(true)
    expect(form.find('.bms-skeleton-control').exists()).toBe(true)
  })

  it('animated=false 无动画类', () => {
    expect(mountSkeleton({ animated: true }).find('.is-animated').exists()).toBe(true)
    expect(mountSkeleton({ animated: false }).find('.is-animated').exists()).toBe(false)
  })

  it('loading=false 渲染默认插槽内容', () => {
    const wrapper = mountWithPlugins(SkeletonBlock, {
      props: { loading: false },
      slots: { default: '<span class="slot-content">实际内容</span>' },
    })
    expect(wrapper.find('.slot-content').exists()).toBe(true)
    expect(wrapper.find('.bms-skeleton').exists()).toBe(false)
  })
})
