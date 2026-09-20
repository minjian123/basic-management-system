<script setup lang="ts">
// 大屏组件渲染件（08-9-2）：按类型分发；图表复用 07_06 ChartRenderer、数据表复用 07_01 DataTable，其余轻量自绘。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  normalizeChartConfig,
  type ChartConfig,
  type ChartDatasetResult,
  type ChartField,
  type ReportDataset,
  type ScreenComponent,
} from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'
import ChartRenderer from '../chart/ChartRenderer.vue'
import DataTable from '../data/DataTable.vue'

interface Props {
  /** 组件模型。 */
  component?: ScreenComponent
  /** 数据集清单（图表字段映射用）。 */
  datasets?: ReportDataset[]
  /** 组件取数结果。 */
  data?: ChartDatasetResult
  /** 只读。 */
  readOnly?: boolean
  /** 渲染模式（设计 / 播放）。 */
  mode?: 'design' | 'play'
}

const props = withDefaults(defineProps<Props>(), {
  component: undefined,
  datasets: () => [],
  data: undefined,
  readOnly: false,
  mode: 'design',
})

const { state, setState } = useBaseDataState()
watch(
  () => props.component !== undefined,
  (has) => setState(has ? 'ready' : 'empty'),
  { immediate: true },
)

/** 组件类型。 */
const widgetType = computed(() => props.component?.type ?? 'text')
/** 数据集字段。 */
const fields = computed<ChartField[]>(() => {
  const item = props.component
  if (item?.datasetId === undefined || item.datasetId === '') {
    return []
  }
  const dataset = props.datasets.find((entry) => entry.id === item.datasetId)
  return (dataset?.fields ?? []) as ChartField[]
})
/** 图表配置。 */
const chartConfig = computed<ChartConfig>(() => {
  const item = props.component
  const existing = item?.config as unknown as Partial<ChartConfig> | undefined
  return normalizeChartConfig({ chartType: item?.chartType ?? 'line', ...(existing ?? {}) }, fields.value)
})
/** 表格列。 */
const tableColumns = computed(() =>
  (props.data?.columns ?? fields.value).map((column) => ({ key: column.name, title: column.name })),
)
/** 表格行。 */
const tableRows = computed(() => props.data?.rows ?? [])
/** 指标值（首个数值单元格）。 */
const metricValue = computed(() => {
  const first = (props.data?.rows ?? [])[0]
  if (first === undefined) {
    return '—'
  }
  const numeric = Object.values(first).find((value) => typeof value === 'number')
  return numeric !== undefined ? String(numeric) : String(Object.values(first)[0] ?? '—')
})
/** 图片地址。 */
const imageSrc = computed(() => String((props.component?.props as { src?: unknown } | undefined)?.src ?? ''))
/** 文本内容。 */
const textValue = computed(() => props.component?.text ?? '')
/** 当前时间文本（播放态每秒刷新）。 */
const nowText = ref('')
let timer: ReturnType<typeof setInterval> | undefined

/** 刷新当前时间。 */
function refreshNow(): void {
  nowText.value = new Date().toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  refreshNow()
  if (props.mode === 'play') {
    timer = setInterval(refreshNow, 1000)
  }
})

onBeforeUnmount(() => {
  if (timer !== undefined) {
    clearInterval(timer)
  }
})
</script>

<template>
  <div class="bms-screen-widget" :data-test="`widget-${widgetType}`" :data-state="state" :data-widget-type="widgetType">
    <ChartRenderer v-if="widgetType === 'chart'" :ready="true" :config="chartConfig" :data="data" :height="0" />
    <DataTable
      v-else-if="widgetType === 'table'"
      :ready="true"
      :columns="tableColumns"
      :data="tableRows"
      :page-size="20"
      :degrade-text="'表格数据未就绪（占位）'"
    />
    <div v-else-if="widgetType === 'metric'" class="bms-screen-widget__metric" data-test="widget-metric">
      <span class="bms-screen-widget__number">{{ metricValue }}</span>
      <span v-if="textValue !== ''" class="bms-screen-widget__unit">{{ textValue }}</span>
    </div>
    <p v-else-if="widgetType === 'text'" class="bms-screen-widget__text" data-test="widget-text">{{ textValue }}</p>
    <img v-else-if="widgetType === 'image'" class="bms-screen-widget__image" data-test="widget-image" :src="imageSrc" alt="" />
    <p v-else-if="widgetType === 'time'" class="bms-screen-widget__time" data-test="widget-time">{{ nowText }}</p>
    <div v-else class="bms-screen-widget__decor" data-test="widget-decor" />
  </div>
</template>

<style scoped>
.bms-screen-widget {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.bms-screen-widget__metric {
  display: flex;
  align-items: baseline;
  gap: 8px;
  height: 100%;
  padding: 8px;
}
.bms-screen-widget__number {
  font-size: 32px;
  font-weight: 600;
}
.bms-screen-widget__unit {
  color: var(--bms-color-text-secondary);
  font-size: 14px;
}
.bms-screen-widget__text {
  margin: 0;
  padding: 8px;
  font-size: 16px;
}
.bms-screen-widget__image {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.bms-screen-widget__time {
  margin: 0;
  padding: 8px;
  font-size: 18px;
}
.bms-screen-widget__decor {
  width: 100%;
  height: 100%;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md, 4px);
}
</style>
