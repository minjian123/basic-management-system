// kiwi_id: 775
/** 图表卡用例（07-6）：投影薄适配 + 基础图表件四态与内核装载 + 图表卡真实实现 + 分包边界。 */

import type { ChartEngineAdapter } from '@bms/core'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ChartCard from '../src/components/chart/ChartCard.vue'
import ChartRenderer from '../src/components/chart/ChartRenderer.vue'
import { useBaseChart } from '../src'

/** 数据集结果。 */
const data = {
  columns: [
    { name: 'month', type: 'text' },
    { name: 'receipt', type: 'number' },
  ],
  rows: [
    { month: '1月', receipt: 12000 },
    { month: '2月', receipt: 18000 },
  ],
}

/** 图表配置。 */
const config = {
  version: 1,
  chartType: 'bar' as const,
  title: '销售趋势',
  mapping: { dimension: 'month', metrics: ['receipt'] },
}

/** 引擎桩（记录调用轨迹）。 */
function makeStub(): { calls: string[]; engine: ChartEngineAdapter } {
  const calls: string[] = []
  return {
    calls,
    engine: {
      init: () => calls.push('init'),
      update: (_option, replace) => calls.push(`update:${replace ? 'replace' : 'merge'}`),
      applyTheme: () => calls.push('applyTheme'),
      resize: () => calls.push('resize'),
      exportImage: () => 'data:image/png;base64,stub',
      dispose: () => calls.push('dispose'),
    },
  }
}

describe('useBaseChart 投影', () => {
  it('占位态降级且取数零请求', async () => {
    const base = useBaseChart()
    expect(base.ready.value).toBe(false)
    expect(base.degraded.value).toBe(true)
    await base.load({ datasetId: 'd1' })
    expect(base.requestCount.value).toBe(0)
  })

  it('就绪后写入配置与数据并生成选项', () => {
    const stub = makeStub()
    const base = useBaseChart({ ready: true, config, result: data })
    base.setEngine(stub.engine)
    expect(base.ready.value).toBe(true)
    expect(base.degraded.value).toBe(false)
    expect(base.option.value).toBeDefined()
    expect(stub.calls).toContain('init')
  })
})

describe('ChartRenderer 基础图表件', () => {
  it('未就绪降级占位，且带分包标记', () => {
    const wrapper = mount(ChartRenderer, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('图表数据未就绪')
    expect(wrapper.attributes('data-subpackage')).toBe('chart-kernel')
  })

  it('就绪态装载引擎并渲染画布', async () => {
    const stub = makeStub()
    const wrapper = mount(ChartRenderer, {
      props: { ready: true, data, config, engineFactory: async () => stub.engine },
    })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.find('[data-test="canvas"]').attributes('data-chart-type')).toBe('bar')
    expect(stub.calls).toContain('init')
  })

  it('空数据不初始化引擎', async () => {
    const stub = makeStub()
    const wrapper = mount(ChartRenderer, {
      props: { ready: true, data: { columns: data.columns, rows: [] }, config, engineFactory: async () => stub.engine },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true)
    expect(stub.calls).not.toContain('init')
  })

  it('加载态渲染骨架', () => {
    const loading = mount(ChartRenderer, { props: { ready: true, loading: true } })
    expect(loading.find('[data-test="loading"]').exists()).toBe(true)
  })

  it('卸载释放引擎', async () => {
    const stub = makeStub()
    const wrapper = mount(ChartRenderer, {
      props: { ready: true, data, config, engineFactory: async () => stub.engine },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    wrapper.unmount()
    expect(stub.calls).toContain('dispose')
  })
})

describe('ChartCard 图表卡', () => {
  it('未就绪降级占位', () => {
    const wrapper = mount(ChartCard, { props: { title: '销售趋势' } })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('图表数据未就绪')
  })

  it('就绪态渲染卡头、图表容器与卡头事件', async () => {
    const wrapper = mount(ChartCard, { props: { ready: true, title: '销售趋势', chartType: 'bar' } })
    expect(wrapper.find('[data-test="title"]').text()).toBe('销售趋势')
    expect(wrapper.find('[data-test="chart"]').attributes('data-chart-type')).toBe('bar')

    await wrapper.find('[data-test="refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    await wrapper.find('[data-test="download"]').trigger('click')
    expect(wrapper.emitted('download')).toHaveLength(1)
    await wrapper.find('[data-test="chart"]').trigger('click')
    expect(wrapper.emitted('chart-click')).toHaveLength(1)
  })

  it('注入引擎工厂后渲染画布并支持视图切换', async () => {
    const stub = makeStub()
    const wrapper = mount(ChartCard, {
      props: { ready: true, title: '销售', config, data, engineFactory: async () => stub.engine, showViewSwitch: true },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.find('[data-test="canvas"]').exists()).toBe(true)
    expect(stub.calls).toContain('init')

    await wrapper.find('[data-test="view-table"]').trigger('click')
    expect(wrapper.emitted('update:view')?.[0]).toEqual(['table'])
  })

  it('脚注展示数据集标注与最后更新', () => {
    const wrapper = mount(ChartCard, {
      props: { ready: true, title: '销售', datasetName: '销售月报', datasetRemark: '含税', updatedAt: '2026-09-19' },
    })
    expect(wrapper.find('[data-test="dataset-name"]').text()).toContain('销售月报')
    expect(wrapper.find('[data-test="updated-at"]').text()).toContain('2026-09-19')
  })

  it('详情 / 移除 / 状态事件', async () => {
    const wrapper = mount(ChartCard, { props: { ready: true, title: '销售', showDetail: true, editable: true, datasetId: 'd1', data } })
    await wrapper.find('[data-test="detail"]').trigger('click')
    expect(wrapper.emitted('detail')?.[0]).toEqual([{ datasetId: 'd1' }])
    await wrapper.find('[data-test="remove"]').trigger('click')
    expect(wrapper.emitted('remove')).toHaveLength(1)
    expect(wrapper.emitted('state-change')).toBeTruthy()
  })
})
