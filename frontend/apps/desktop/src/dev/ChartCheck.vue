<script setup lang="ts">
// 开发态核对页（07_06）：图表卡（类型集 / 数据映射 / 风格 / 视图切换 / 四态 / 令牌主题 / 脚注）实例 + 12 项自检上屏（本页不进构建产物）。
import type { ChartConfig, ChartDatasetResult } from '@bms/core'
import { ChartCard } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 演示数据集结果。 */
const data: ChartDatasetResult = {
  columns: [
    { name: 'month', type: 'text' },
    { name: 'receipt', type: 'number' },
    { name: 'payment', type: 'number' },
  ],
  rows: [
    { month: '1月', receipt: 12000, payment: 8000 },
    { month: '2月', receipt: 18000, payment: 9000 },
    { month: '3月', receipt: 15000, payment: 11000 },
    { month: '4月', receipt: 22000, payment: 10000 },
    { month: '5月', receipt: 26000, payment: 14000 },
    { month: '6月', receipt: 24000, payment: 15000 },
  ],
}

/** 演示配置。 */
const config = ref<ChartConfig>({
  version: 1,
  chartType: 'bar',
  title: '销售趋势',
  mapping: { dimension: 'month', metrics: ['receipt', 'payment'] },
  style: { legend: true, smooth: false, stacked: false, label: false, paletteIndex: 0 },
})

/** 就绪态。 */
const ready = ref(true)
/** 视图。 */
const view = ref<'chart' | 'table'>('chart')
/** 深色。 */
const dark = ref(false)
/** 刷新 / 导出 / 详情 / 移除 交互计数。 */
const counters = ref({ refresh: 0, download: 0, detail: 0, remove: 0 })

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

/** 等待渲染与异步结算。 */
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
  for (let i = 0; i < 60; i += 1) {
    if (q(scope, selector) !== null) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
}

/**
 * 点击元素（缺失时跳过）。
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

/** 切换图表类型。 */
async function setKind(kind: string): Promise<void> {
  config.value = { ...config.value, chartType: kind as ChartConfig['chartType'] }
  await settle()
}

/** 切换深浅主题。 */
async function toggleDark(): Promise<void> {
  dark.value = !dark.value
  document.documentElement.dataset.theme = dark.value ? 'dark' : 'light'
  await settle()
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  await waitFor('chart', '[data-test="chart"]')
  await waitFor('chart', '[data-test="canvas"] canvas')

  result.push({ label: '① 就绪态渲染卡头与标题', pass: q('chart', '[data-test="header"]') !== null && q('chart', '[data-test="title"]')?.textContent === '销售趋势' })
  result.push({ label: '② 图表容器渲染且 data-chart-type 正确', pass: q('chart', '[data-test="chart"]')?.getAttribute('data-chart-type') === 'bar' })
  result.push({ label: '③ ECharts 画布已初始化（独立分包内核装载）', pass: q('chart', '[data-test="canvas"] canvas') !== null })

  await setKind('pie')
  result.push({ label: '④ 类型集切换（柱 → 饼，容器类型与画布重建）', pass: q('chart', '[data-test="chart"]')?.getAttribute('data-chart-type') === 'pie' })
  await setKind('bar')

  result.push({ label: '⑤ 图表渲染件标记分包入口', pass: q('chart', '[data-test="chart-renderer"]')?.getAttribute('data-subpackage') === 'chart-kernel' })

  await click('chart', '[data-test="view-table"]')
  result.push({ label: '⑥ 视图切换（图表 → 数据表）', pass: q('chart', '[data-test="data-table"]') !== null })
  await click('chart', '[data-test="view-chart"]')

  await toggleDark()
  result.push({ label: '⑦ 深浅主题切换（根 data-theme=dark，画布保持）', pass: document.documentElement.dataset.theme === 'dark' && q('chart', '[data-test="canvas"] canvas') !== null })
  await toggleDark()

  result.push({ label: '⑧ 脚注数据集标注与最后更新', pass: q('chart', '[data-test="dataset-name"]') !== null && q('chart', '[data-test="updated-at"]') !== null })

  await click('chart', '[data-test="refresh"]')
  result.push({ label: '⑨ 卡头刷新上抛', pass: counters.value.refresh > 0 })

  await click('chart', '[data-test="download"]')
  result.push({ label: '⑩ 卡头导出上抛', pass: counters.value.download > 0 })

  await click('chart', '[data-test="detail"]')
  await click('chart', '[data-test="remove"]')
  result.push({ label: '⑪ 查看详情与编辑态移除上抛', pass: counters.value.detail > 0 && counters.value.remove > 0 })

  ready.value = false
  await settle()
  const placeholder = q('chart', '[data-test="placeholder"]')
  result.push({ label: '⑫ 未就绪降级占位（数据通路未就绪）', pass: placeholder !== null && (placeholder.textContent ?? '').includes('图表数据未就绪') })
  ready.value = true
  await settle()

  checks.value = result
  document.body.setAttribute('data-check-done', result.every((item) => item.pass) ? 'pass' : 'fail')
}

onMounted(() => {
  void runChecks()
})
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>图表卡核对页（07-6）</h1>
    <section data-check-scope="chart">
      <ChartCard
        :ready="ready"
        :data="data"
        :config="config"
        :chart-type="config.chartType"
        :title="config.title ?? ''"
        :view="view"
        dataset-name="销售月报"
        dataset-remark="口径：含税"
        updated-at="2026-09-19 10:00"
        :show-detail="true"
        :editable="true"
        :height="320"
        @refresh="counters.refresh += 1"
        @download="counters.download += 1"
        @detail="counters.detail += 1"
        @remove="counters.remove += 1"
        @update:view="view = $event"
      />
    </section>

    <section style="margin-top: 16px">
      <button type="button" @click="ready = !ready">切换就绪 / 降级</button>
      <button type="button" @click="toggleDark">切换深浅</button>
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
