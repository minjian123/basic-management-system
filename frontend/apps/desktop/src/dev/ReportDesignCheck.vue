<script setup lang="ts">
// 开发态核对页（08_09_01）：报表设计器（三区 / 数据集选择与预览 / 新增图表 / 配置与映射 / 网格落点 / 复制居中删除 / 脏基线 / 保存发布另存）实例 + 12 项自检上屏（本页不进构建产物）。
import type { ReportChartItem, ReportDataset, ReportJobs } from '@bms/core'
import { ReportDesigner } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 演示数据集。 */
const datasets: ReportDataset[] = [
  {
    id: 'd1',
    code: 'sales_monthly',
    name: '销售月报',
    status: 'enabled',
    fields: [
      { name: 'month', type: 'text' },
      { name: 'receipt', type: 'number' },
    ],
  },
  { id: 'd2', code: 'stopped', name: '已停用', status: 'disabled', fields: [{ name: 'region', type: 'text' }] },
]

/** 初始图表项。 */
const initialCharts: ReportChartItem[] = [
  { id: 'chart-1', datasetId: 'd1', chartType: 'bar', title: '销售趋势', layout: { x: 0, y: 0, w: 6, h: 4 } },
]

/** 处理函数调用轨迹。 */
const calls: string[] = []
const jobs: ReportJobs = {
  load: async () => {
    calls.push('load')
    return { code: 'sales_report', name: '销售月报', charts: initialCharts }
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
    return {
      columns: [
        { name: 'month', type: 'text' },
        { name: 'receipt', type: 'number' },
      ],
      rows: [
        { month: '1月', receipt: 12000 },
        { month: '2月', receipt: 18000 },
      ],
    }
  },
}

/** 设计器实例。 */
const designerRef = ref<InstanceType<typeof ReportDesigner>>()
/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/**
 * 作用域内查询元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function q(scope: string, selector: string): Element | null {
  return document.querySelector(`[data-check-scope="${scope}"] ${selector}`)
}

/** 等待渲染与异步结算（含懒加载分包件到位）。 */
async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 30))
    await nextTick()
  }
}

/**
 * 等待元素出现。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function waitFor(scope: string, selector: string): Promise<void> {
  for (let i = 0; i < 80; i += 1) {
    if (q(scope, selector) !== null) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
}

/**
 * 点击元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function click(scope: string, selector: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLElement) {
    element.click()
  }
  await settle()
}

/**
 * 设置下拉 / 输入值。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 * @param value 取值。
 */
async function setValue(scope: string, selector: string, value: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLSelectElement || element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    element.value = value
    element.dispatchEvent(new Event('change'))
    element.dispatchEvent(new Event('input'))
  }
  await settle()
}

/** 设计器内部状态读取（演示核对用）。 */
interface DesignerInner {
  /** 图表项清单。 */
  charts: ReportChartItem[]
  /** 是否脏。 */
  dirty: boolean
  /** 移动图表项。 */
  moveChart: (id: string, x: number, y: number) => boolean
  /** 撤销。 */
  discard: () => boolean
  /** 是否拦截。 */
  needsBlock: (action: string) => boolean
  /** 另存为。 */
  saveAs: (code: string) => Promise<unknown>
}

function inner(): DesignerInner | undefined {
  return (designerRef.value as unknown as { designer?: DesignerInner } | undefined)?.designer
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  await waitFor('designer', '[data-test="report-canvas"]')
  await waitFor('designer', '[data-test="chart-chart-1"]')

  result.push({
    label: '① 三区渲染（数据集 / 画布 / 配置）',
    pass:
      q('designer', '[data-test="dataset-panel"]') !== null &&
      q('designer', '[data-test="report-canvas"]') !== null &&
      q('designer', '[data-test="config-panel"]') !== null,
  })

  result.push({
    label: '② 停用数据集不可选',
    pass: q('designer', '[data-test="dataset-d2"]')?.hasAttribute('disabled') === true && q('designer', '[data-test="dataset-d1"]') !== null,
  })

  await click('designer', '[data-test="dataset-d1"]')
  result.push({
    label: '③ 新增图表卡（选数据集）',
    pass: (inner()?.charts.length ?? 0) === 2,
  })

  result.push({
    label: '④ 字段清单渲染',
    pass: q('designer', '[data-test="field-month"]') !== null && q('designer', '[data-test="field-receipt"]') !== null,
  })

  await click('designer', '[data-test="preview-trigger"]')
  result.push({
    label: '⑤ 数据预览取数（只读从库口径）',
    pass: q('designer', '[data-test="preview-table"]') !== null && calls.includes('preview'),
  })

  await click('designer', '[data-test="chart-chart-1"]')
  result.push({
    label: '⑥ 选中联动与配置面板显示类型',
    pass: q('designer', '[data-test="config-selected"]')?.textContent === 'bar',
  })

  await setValue('designer', '[data-test="config-type"]', 'pie')
  result.push({
    label: '⑦ 图表类型切换回写',
    pass: inner()?.charts.find((item) => item.id === 'chart-1')?.chartType === 'pie',
  })

  await setValue('designer', '[data-test="config-title"]', '改后标题')
  await setValue('designer', '[data-test="config-axis-name"]', '金额')
  result.push({
    label: '⑧ 标题与常用样式回写',
    pass: inner()?.charts.find((item) => item.id === 'chart-1')?.title === '改后标题',
  })

  inner()?.moveChart('chart-1', 6, 0)
  await settle()
  result.push({
    label: '⑨ 网格落点回写（gs-x）',
    pass: q('designer', '[data-test="grid-item-chart-1"]')?.getAttribute('gs-x') === '6',
  })

  await click('designer', '[data-test="chart-duplicate-chart-1"]')
  result.push({
    label: '⑩ 复制图表卡',
    pass: (inner()?.charts.length ?? 0) === 3,
  })

  await click('designer', '[data-test="remove-chart-1"]')
  result.push({
    label: '⑪ 删除图表卡',
    pass: (inner()?.charts.some((item) => item.id === 'chart-1') ?? true) === false,
  })

  await click('designer', '[data-test="open"]')
  await click('designer', '[data-test="dataset-d1"]')
  const dirtyBefore = inner()?.dirty ?? false
  const discarded = inner()?.discard() ?? false
  await click('designer', '[data-test="save"]')
  await click('designer', '[data-test="publish"]')
  await inner()?.saveAs('copy_report')
  await settle()
  result.push({
    label: '⑫ 脏基线与撤销（保存 / 发布 / 另存链路可用）',
    pass:
      dirtyBefore &&
      discarded &&
      !(inner()?.dirty ?? true) &&
      calls.includes('save') &&
      calls.includes('publish') &&
      calls.includes('saveAs'),
  })

  checks.value = result
  document.body.setAttribute('data-check-done', result.every((item) => item.pass) ? 'pass' : 'fail')
}

onMounted(() => {
  void runChecks()
})
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>报表设计器核对页（08-9-1）</h1>
    <section data-check-scope="designer">
      <ReportDesigner
        ref="designerRef"
        :ready="true"
        report-code="sales_report"
        report-name="销售月报"
        :datasets="datasets"
        :charts="initialCharts"
        :jobs="jobs"
      />
    </section>

    <section style="margin-top: 16px">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass">
          {{ item.pass ? '通过' : '失败' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>
