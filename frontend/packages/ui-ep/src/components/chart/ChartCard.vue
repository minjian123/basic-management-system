<script setup lang="ts">
// 图表卡（07_06）：工作台图表卡容器——卡头 / 视图切换 / 取数编排 / 四态 / 脚注 / 导出。
// 对外契约保持 07_01 冻结形状（导出名 / 既有 Props / 事件 / 插槽 / data-test 不变），仅向后兼容新增可选项。
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'

import type {
  ChartConfig,
  ChartDatasetResult,
  ChartEngineAdapter,
  ChartJobs,
  ChartKind,
  ChartMapping,
  ChartRenderMode,
  ChartStyleOptions,
  ChartThemeMode,
  ChartTokenReader,
  ChartView,
} from '@bms/core'

import { useBaseChart } from '../../composables/useBaseChart'
import DataTable from '../data/DataTable.vue'
import ChartRenderer from './ChartRenderer.vue'

/** 图表类型（沿用 07_01 导出名；值域与图表域 `ChartKind` 同源）。 */
export type ChartType = ChartKind

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 卡标题。 */
  title?: string
  /** 图表类型。 */
  chartType?: ChartType
  /** 完整图表配置（ECharts option）。 */
  option?: Record<string, unknown>
  /** 加载中。 */
  loading?: boolean
  /** 卡片高度（px）。 */
  height?: number
  /** 降级文案。 */
  degradeText?: string
  /** 数据集标识（注入 `jobs` 后取数）。 */
  datasetId?: string
  /** 数据集名称（脚注标注）。 */
  datasetName?: string
  /** 数据集口径说明（脚注）。 */
  datasetRemark?: string
  /** 数据集结果（由宿主下发时直接渲染）。 */
  data?: ChartDatasetResult
  /** 数据映射。 */
  mapping?: ChartMapping
  /** 常用样式。 */
  chartStyle?: ChartStyleOptions
  /** 图表配置（优先于类型 + 映射 + 样式）。 */
  config?: ChartConfig
  /** 主题模式。 */
  themeMode?: ChartThemeMode
  /** 渲染模式。 */
  renderMode?: ChartRenderMode
  /** 视图（图表 / 数据表）。 */
  view?: ChartView
  /** 是否显示视图切换。 */
  showViewSwitch?: boolean
  /** 是否显示刷新。 */
  showRefresh?: boolean
  /** 是否显示查看详情。 */
  showDetail?: boolean
  /** 轮询间隔（秒，0 不轮询）。 */
  pollInterval?: number
  /** 编辑态（显示移除）。 */
  editable?: boolean
  /** 最后更新时间（脚注）。 */
  updatedAt?: string
  /** 取数处理函数（注入后驱动真实取数）。 */
  jobs?: ChartJobs
  /** 令牌读取口。 */
  tokens?: ChartTokenReader
  /** 深色偏好。 */
  prefersDark?: boolean
  /** 引擎工厂（测试注入）。 */
  engineFactory?: () => Promise<ChartEngineAdapter>
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  title: '',
  chartType: 'line',
  option: undefined,
  loading: false,
  height: 300,
  degradeText: '图表数据未就绪（占位）',
  datasetId: '',
  datasetName: '',
  datasetRemark: '',
  data: undefined,
  mapping: undefined,
  chartStyle: undefined,
  config: undefined,
  themeMode: 'auto',
  renderMode: 'canvas',
  view: 'chart',
  showViewSwitch: true,
  showRefresh: true,
  showDetail: false,
  pollInterval: 0,
  editable: false,
  updatedAt: '',
  jobs: undefined,
  tokens: undefined,
  prefersDark: false,
  engineFactory: undefined,
})

const emit = defineEmits<{
  refresh: []
  'chart-click': [params: Record<string, unknown>]
  download: []
  'update:view': [view: ChartView]
  detail: [params: Record<string, unknown>]
  remove: []
  'state-change': [state: string]
  loaded: [result: ChartDatasetResult]
  failed: [{ message: string }]
}>()

/** 由类型 + 映射 + 样式派生的配置。 */
const derivedConfig = computed<ChartConfig>(() => ({
  version: 1,
  chartType: props.chartType,
  ...(props.title !== '' ? { title: props.title } : {}),
  mapping: props.mapping ?? { metrics: [] },
  ...(props.chartStyle !== undefined ? { style: props.chartStyle } : {}),
}))

const base = useBaseChart({
  ready: props.ready,
  config: props.config ?? derivedConfig.value,
  result: props.data,
  option: props.option,
  themeMode: props.themeMode,
  renderMode: props.renderMode,
  height: props.height,
  tokens: props.tokens,
  prefersDark: props.prefersDark,
  jobs: props.jobs ?? {},
})

/** 当前视图（受控优先）。 */
const view = computed<ChartView>(() => props.view)

/** 是否具备可渲染输入（无输入时保持卡壳占位，不装载图表内核）。 */
const renderable = computed(
  () => props.option !== undefined || props.data !== undefined || props.config !== undefined || props.jobs !== undefined,
)

/** 数据表列。 */
const tableColumns = computed(() => (props.data?.columns ?? []).map((column) => ({ key: column.name, title: column.name })))

watch(
  () => props.ready,
  (value) => base.setReady(value),
)
watch(
  () => props.chartType,
  (value) => base.setChartType(value),
)
watch(
  () => props.mapping,
  (value) => {
    if (value !== undefined) {
      base.setMapping(value)
    }
  },
)
watch(
  () => props.config,
  (value) => {
    if (value !== undefined) {
      base.setConfig(value)
    }
  },
)
watch(
  () => props.data,
  (value) => base.setResult(value),
)
watch(
  () => props.view,
  (value) => base.setView(value),
)
watch(
  () => props.themeMode,
  (value) => base.setThemeMode(value),
)
watch([() => props.ready, () => props.datasetId], () => {
  if (props.ready && props.jobs !== undefined && props.datasetId !== '') {
    void base.load({ datasetId: props.datasetId })
  }
})
watch(
  () => base.state.value,
  (value) => emit('state-change', value),
  { immediate: true },
)

/** 轮询定时器。 */
let timer: ReturnType<typeof setInterval> | undefined

/** 页面可见时才轮询。 */
function startPoll(): void {
  if (props.pollInterval <= 0 || timer !== undefined) {
    return
  }
  timer = setInterval(() => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      return
    }
    emit('refresh')
  }, props.pollInterval * 1000)
}

onMounted(() => {
  startPoll()
})

onBeforeUnmount(() => {
  if (timer !== undefined) {
    clearInterval(timer)
    timer = undefined
  }
})

/** 切换视图。 */
function switchView(next: ChartView): void {
  base.setView(next)
  emit('update:view', next)
}

/** 数据点点击。 */
function onChartClick(params: Record<string, unknown>): void {
  emit('chart-click', params)
}

/** 刷新。 */
function onRefresh(): void {
  emit('refresh')
  if (props.jobs !== undefined && props.datasetId !== '') {
    void base.load({ datasetId: props.datasetId }).then((result) => {
      if (result !== undefined) {
        emit('loaded', result)
      } else if (base.chart.errorMessage !== '') {
        emit('failed', { message: base.chart.errorMessage })
      }
    })
  }
}
</script>

<template>
  <div
    class="bms-chart-card"
    :data-ready="base.ready.value"
    :data-degraded="base.degraded.value"
    :data-view="view"
  >
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-chart-card__header" data-test="header">
        <span class="bms-chart-card__title" data-test="title">{{ title }}</span>
        <div class="bms-chart-card__actions">
          <slot name="header-actions" />
          <button v-if="showViewSwitch" type="button" data-test="view-chart" :disabled="view === 'chart'" @click="switchView('chart')">
            图表
          </button>
          <button v-if="showViewSwitch" type="button" data-test="view-table" :disabled="view === 'table'" @click="switchView('table')">
            数据表
          </button>
          <slot name="actions" />
          <button v-if="showRefresh" type="button" data-test="refresh" @click="onRefresh">刷新</button>
          <button v-if="showDetail" type="button" data-test="detail" @click="emit('detail', { datasetId })">详情</button>
          <button v-if="editable" type="button" data-test="remove" @click="emit('remove')">移除</button>
          <button type="button" data-test="download" @click="emit('download')">导出</button>
        </div>
      </div>
      <div
        v-if="view === 'chart'"
        class="bms-chart-card__body"
        :style="{ height: `${height}px` }"
        :data-chart-type="chartType"
        data-test="chart"
        @click="onChartClick({ chartType, option })"
      >
        <slot name="live" :chart-type="chartType" :option="option">
          <ChartRenderer
            v-if="renderable"
            :ready="base.ready.value"
            :option="option"
            :chart-type="chartType"
            :data="data"
            :config="config"
            :theme-mode="themeMode"
            :render-mode="renderMode"
            :loading="loading"
            :height="height"
            :engine-factory="engineFactory"
            @retry="emit('refresh')"
          />
          <span v-else data-test="chart-holder">图表（{{ chartType }}）</span>
        </slot>
      </div>
      <div v-else class="bms-chart-card__table" data-test="data-table">
        <slot name="live" :chart-type="chartType" :option="option">
          <DataTable :ready="base.ready.value" :columns="tableColumns" :data="data?.rows ?? []" />
        </slot>
      </div>
      <div v-if="datasetName !== '' || updatedAt !== ''" class="bms-chart-card__footnote" data-test="footnote">
        <span v-if="datasetName !== ''" data-test="dataset-name">{{ datasetName }}<template v-if="datasetRemark !== ''"> · {{ datasetRemark }}</template></span>
        <span v-if="updatedAt !== ''" data-test="updated-at">最后更新：{{ updatedAt }}</span>
      </div>
    </template>
  </div>
</template>
