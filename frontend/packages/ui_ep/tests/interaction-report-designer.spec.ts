// kiwi_id: 776
/** 报表设计器用例（08-9-1）：投影薄适配 + 四件真实实现 + 数据集/配置联动 + 分包边界。 */

import type { ReportChartItem, ReportDataset, ReportJobs } from '@bms/core'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ChartConfigPanel from '../src/components/report/ChartConfigPanel.vue'
import DatasetPanel from '../src/components/report/DatasetPanel.vue'
import ReportCanvas from '../src/components/report/ReportCanvas.vue'
import ReportGrid from '../src/components/report/ReportGrid.vue'
import ReportDesigner from '../src/components/report/ReportDesigner.vue'
import { useBaseReportDesigner } from '../src'

/** 数据集。 */
const datasets: ReportDataset[] = [
  {
    id: 'd1',
    code: 'sales',
    name: '销售',
    status: 'enabled',
    fields: [
      { name: 'month', type: 'text' },
      { name: 'receipt', type: 'number' },
    ],
  },
  { id: 'd2', code: 'stock', name: '库存', status: 'disabled' },
]

/** 图表项。 */
const charts: ReportChartItem[] = [{ id: 'ch1', datasetId: 'd1', chartType: 'bar', title: '销售趋势', layout: { x: 0, y: 0, w: 6, h: 4 } }]

/** 处理函数集。 */
function makeJobs(): { jobs: ReportJobs; calls: string[] } {
  const calls: string[] = []
  return {
    calls,
    jobs: {
      load: async () => {
        calls.push('load')
        return { code: 'sales_report', name: '销售月报', charts }
      },
      save: async () => {
        calls.push('save')
        return { recordVersion: 2 }
      },
      publish: async () => {
        calls.push('publish')
      },
      saveAs: async () => {
        calls.push('saveAs')
        return { recordVersion: 1 }
      },
      preview: async () => {
        calls.push('preview')
        return { columns: [{ name: 'month', type: 'text' }], rows: [{ month: '1月' }] }
      },
    },
  }
}

describe('useBaseReportDesigner 投影', () => {
  it('占位态降级且零请求', async () => {
    const base = useBaseReportDesigner()
    expect(base.ready.value).toBe(false)
    expect(base.degraded.value).toBe(true)
    await base.load()
    expect(base.requestCount.value).toBe(0)
  })

  it('就绪后注入处理函数驱动取数与增删', async () => {
    const { jobs } = makeJobs()
    const base = useBaseReportDesigner({ ready: true, datasets, charts, jobs })
    await base.load()
    expect(base.requestCount.value).toBe(1)
    expect(base.charts.value).toHaveLength(1)

    base.selectDataset('d1')
    base.addChart({ datasetId: 'd1', chartType: 'line' })
    expect(base.charts.value).toHaveLength(2)
    expect(base.dirty.value).toBe(true)
  })
})

describe('DatasetPanel 数据集详情', () => {
  it('渲染字段清单与预览', () => {
    const wrapper = mount(DatasetPanel, {
      props: {
        dataset: datasets[0],
        datasetId: 'd1',
        previewColumns: [{ name: 'month', type: 'text' }],
        previewRows: [{ month: '1月' }],
      },
    })
    expect(wrapper.find('[data-test="field-month"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="preview-table"]').text()).toContain('1月')
  })

  it('停用提示与预览触发', async () => {
    const wrapper = mount(DatasetPanel, { props: { dataset: datasets[1], datasetId: 'd2' } })
    expect(wrapper.find('[data-test="dataset-disabled-hint"]').exists()).toBe(true)
    await wrapper.find('[data-test="preview-trigger"]').trigger('click')
    expect(wrapper.emitted('preview')?.[0]).toEqual([{ datasetId: 'd2' }])
  })
})

describe('ChartConfigPanel 图表配置', () => {
  it('未选中空态；选中渲染类型并可切换映射', async () => {
    const empty = mount(ChartConfigPanel, { props: {} })
    expect(empty.find('[data-test="config-empty"]').exists()).toBe(true)

    const wrapper = mount(ChartConfigPanel, { props: { item: charts[0], fields: datasets[0].fields } })
    expect(wrapper.find('[data-test="config-selected"]').text()).toBe('bar')

    await wrapper.find('[data-test="config-type"]').setValue('pie')
    const update = wrapper.emitted('update')?.[0]?.[0] as { patch: { chartType?: string } }
    expect(update.patch.chartType).toBe('pie')
  })
})

describe('ReportCanvas 报表画布', () => {
  it('空态与分包标记', async () => {
    const empty = mount(ReportCanvas, { props: { charts: [] } })
    expect(empty.find('[data-test="canvas-empty"]').exists()).toBe(true)

    const wrapper = mount(ReportCanvas, { props: { charts, datasets } })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.attributes('data-subpackage')).toBe('report')
    expect(wrapper.find('[data-test="chart-ch1"]').exists()).toBe(true)
    await wrapper.find('[data-test="remove-ch1"]').trigger('click')
    expect(wrapper.emitted('remove-chart')?.[0]).toEqual(['ch1'])
  })
})

describe('ReportGrid 网格画布', () => {
  it('渲染网格项并带 gridstack 分包标记', () => {
    const wrapper = mount(ReportGrid, { props: { charts, selectedId: 'ch1' } })
    expect(wrapper.attributes('data-subpackage')).toBe('gridstack')
    expect(wrapper.find('[data-test="grid-item-ch1"]').exists()).toBe(true)
  })
})

describe('ReportDesigner 报表设计器', () => {
  it('未就绪降级占位', () => {
    const wrapper = mount(ReportDesigner, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('报表设计器未就绪')
  })

  it('就绪态三区渲染与事件上抛', async () => {
    const wrapper = mount(ReportDesigner, { props: { ready: true, reportCode: 'r1', datasets, charts, dirty: true } })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="report-code"]').text()).toBe('r1')
    expect(wrapper.find('[data-test="dataset-d2"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="dataset-d1"]').trigger('click')
    expect(wrapper.emitted('add-chart')?.[0]).toEqual([{ datasetId: 'd1', chartType: 'line' }])
    await wrapper.find('[data-test="save"]').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
  })

  it('注入处理函数驱动真实编排', async () => {
    const { jobs, calls } = makeJobs()
    const wrapper = mount(ReportDesigner, {
      props: { ready: true, reportCode: 'r1', datasets, charts, jobs },
    })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="dataset-d1"]').trigger('click')
    expect(calls.includes('save')).toBe(false)
    await wrapper.find('[data-test="save"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(calls).toContain('save')
    expect(wrapper.emitted('saved')).toBeTruthy()

    await wrapper.find('[data-test="publish"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(calls).toContain('publish')
  })

  it('脏数据新建拦截', async () => {
    const { jobs } = makeJobs()
    const wrapper = mount(ReportDesigner, {
      props: { ready: true, datasets, charts, jobs },
    })
    await vi.dynamicImportSettled()
    await wrapper.find('[data-test="open"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.find('[data-test="dataset-d1"]').trigger('click')
    await wrapper.find('[data-test="new"]').trigger('click')
    expect(wrapper.emitted('dirty-block')?.[0]).toEqual([{ action: 'new' }])
  })
})
