// kiwi_id: 958
/** 指标卡用例（07_05）：指标契约 + 占位降级 + 数值与单位 + 趋势状态色 + 迷你趋势折线 + 空态与跳转。 */

import { buildSparkline, formatMetricValue, resolveMetricTrend } from '@bms/core'
import { describeMetricContract, type MetricContractTarget } from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { MetricCard } from '../src'

/** 契约目标：指标领域纯函数（ui-ep 侧同契约多实现适配）。 */
const metricTarget: MetricContractTarget = {
  format: (value, options) => formatMetricValue(value, options),
  trend: (compare) => resolveMetricTrend(compare),
  sparkline: (values, options) => buildSparkline(values, options),
}

describeMetricContract('指标契约（ui-ep 适配）', () => metricTarget)

describe('MetricCard 占位与数值', () => {
  it('未就绪时降级且不发请求', () => {
    const wrapper = mount(MetricCard, { props: { title: '待审' } })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('指标数据未就绪')
    expect(wrapper.find('[data-test="metric-value"]').exists()).toBe(false)
  })

  it('数值 / 前缀 / 单位与格式化口径', () => {
    const wrapper = mount(MetricCard, {
      props: { ready: true, title: '本月收款', value: 1234.5, format: 'amount', unit: '笔', animate: false },
    })
    expect(wrapper.find('[data-test="metric-title"]').text()).toBe('本月收款')
    expect(wrapper.find('[data-test="metric-value"]').text()).toBe('¥1,234.50笔')
    expect(wrapper.find('[data-test="metric-unit"]').text()).toBe('笔')

    const prefixed = mount(MetricCard, {
      props: { ready: true, title: '本月收款', value: 1234.5, prefix: '¥', unit: '笔', animate: false },
    })
    expect(prefixed.find('[data-test="metric-value"]').text()).toBe('¥1,234.5笔')
    expect(prefixed.find('[data-test="metric-prefix"]').text()).toBe('¥')

    const compact = mount(MetricCard, {
      props: { ready: true, title: '访问量', value: 12345, compact: true, animate: false },
    })
    expect(compact.find('[data-test="metric-value"]').text()).toBe('1.2万')
  })

  it('口径说明与空态', () => {
    const wrapper = mount(MetricCard, {
      props: { ready: true, title: '含税金额', value: null, caption: '含税金额', animate: false },
    })
    expect(wrapper.find('[data-test="metric-empty"]').text()).toBe('—')
    expect(wrapper.find('[data-test="metric-caption"]').text()).toBe('含税金额')
    expect(wrapper.find('[data-test="metric-value"]').exists()).toBe(false)
  })

  it('加载态渲染骨架', () => {
    const wrapper = mount(MetricCard, { props: { ready: true, title: '待审', value: 1, loading: true } })
    expect(wrapper.find('[data-test="metric-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="metric-value"]').exists()).toBe(false)
  })
})

describe('MetricCard 趋势与迷你趋势图', () => {
  it('环比上升为 success、下降为 danger，令牌引用设计令牌', () => {
    const up = mount(MetricCard, {
      props: { ready: true, title: '收款', value: 100, compare: { kind: 'mom', value: 12.5 }, animate: false },
    })
    expect(up.find('[data-test="metric-compare"]').text()).toContain('较上月 +12.5%')
    expect(up.find('[data-test="metric-compare"]').attributes('style')).toContain('--bms-color-success')

    const down = mount(MetricCard, {
      props: { ready: true, title: '退款', value: 100, compare: { kind: 'yoy', value: -5 }, animate: false },
    })
    expect(down.find('[data-test="metric-compare"]').text()).toContain('较去年同期 -5.0%')
    expect(down.find('[data-test="metric-compare"]').attributes('style')).toContain('--bms-color-danger')
  })

  it('higherIsBetter 反转与持平、可关闭状态色', () => {
    const inverted = mount(MetricCard, {
      props: {
        ready: true,
        title: '逾期率',
        value: 3,
        compare: { kind: 'mom', value: -5, higherIsBetter: false },
        animate: false,
      },
    })
    expect(inverted.find('[data-test="metric-compare"]').attributes('style')).toContain('--bms-color-success')

    const flat = mount(MetricCard, {
      props: { ready: true, title: '存量', value: 3, compare: { kind: 'mom', value: 0 }, animate: false },
    })
    expect(flat.find('[data-test="metric-compare"]').text()).toContain('持平')
    expect(flat.find('[data-test="metric-compare"]').attributes('style')).toContain('--bms-color-info')

    const plain = mount(MetricCard, {
      props: {
        ready: true,
        title: '存量',
        value: 3,
        compare: { kind: 'mom', value: 1 },
        statusColor: false,
        animate: false,
      },
    })
    expect(plain.find('[data-test="metric-compare"]').attributes('style') ?? '').not.toContain('--bms-color')
  })

  it('迷你趋势折线（序列不足或全等值不渲染）', () => {
    const wrapper = mount(MetricCard, {
      props: { ready: true, title: '走势', value: 10, trend: [1, 3, 2, 5], animate: false },
    })
    expect(wrapper.find('[data-test="metric-sparkline"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="metric-sparkline"]').findAll('path')).toHaveLength(2)

    const flat = mount(MetricCard, {
      props: { ready: true, title: '走势', value: 10, trend: [2, 2], animate: false },
    })
    expect(flat.find('[data-test="metric-sparkline"]').exists()).toBe(false)
  })
})

describe('MetricCard 交互', () => {
  it('点击跳转与刷新', async () => {
    const wrapper = mount(MetricCard, {
      props: { ready: true, title: '待审', value: 5, linkTo: '/list/audit', animate: false },
    })
    await wrapper.find('[data-test="metric-value"]').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
    expect(wrapper.emitted('nav')?.[0]).toEqual(['/list/audit'])

    await wrapper.find('[data-test="metric-refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('数字滚动：开启动画时先归零、关闭时直达终值', async () => {
    // 以可控 rAF 帧推进动画：避免依赖真实 requestAnimationFrame 时序（CI 高负载下易偶发超时）
    const frames: FrameRequestCallback[] = []
    const raf = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb) => {
      frames.push(cb)
      return frames.length
    })
    const caf = vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {})
    try {
      const animated = mount(MetricCard, { props: { ready: true, title: '收款', value: 100 } })
      expect(animated.find('[data-test="metric-value"]').text()).toBe('0')

      // 以超出动画时长的帧时间戳推进一步，动画直达终值（不依赖真实时钟）
      while (frames.length > 0) {
        frames.shift()?.(performance.now() + 1000)
      }
      await nextTick()
      expect(animated.find('[data-test="metric-value"]').text()).toBe('100')
    } finally {
      raf.mockRestore()
      caf.mockRestore()
    }

    const still = mount(MetricCard, { props: { ready: true, title: '收款', value: 100, animate: false } })
    expect(still.find('[data-test="metric-value"]').text()).toBe('100')
  })
})
