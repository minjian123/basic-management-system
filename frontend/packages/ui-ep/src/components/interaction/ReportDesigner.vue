<script setup lang="ts">
// 报表设计器（占位版，08_01_03）：契约先行冻结；数据通路未就绪时不请求、编辑禁用 + 降级提示。画布独立分包懒加载。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseOptionSource } from '../../composables/useBaseOptionSource'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 报表画布独立分包（12 列网格 / 图表渲染，真实实现 08_09 接入）。
const ReportCanvas = defineAsyncComponent(() => import('./ReportCanvas.vue'))

/** 数据集。 */
export interface ReportDataset {
  /** 数据集标识。 */
  id: string
  /** 数据集编码。 */
  code: string
  /** 数据集名称。 */
  name: string
  /** 状态。 */
  status: 'enabled' | 'disabled'
  /** 字段清单（数据映射用）。 */
  fields?: { name: string; type: string }[]
}

/** 图表项。 */
export interface ReportChartItem {
  /** 图表项标识。 */
  id: string
  /** 引用数据集标识。 */
  datasetId: string
  /** 图表类型。 */
  chartType: string
  /** 标题。 */
  title?: string
  /** 图表配置覆盖。 */
  config?: Record<string, unknown>
  /** 网格布局坐标与尺寸。 */
  layout: { x: number; y: number; w: number; h: number }
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 报表标识。 */
  reportCode?: string
  /** 数据集清单。 */
  datasets?: ReportDataset[]
  /** 图表项。 */
  charts?: ReportChartItem[]
  /** 当前选中图表项标识。 */
  selectedId?: string
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 只读。 */
  readOnly?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  reportCode: '',
  datasets: () => [],
  charts: () => [],
  selectedId: '',
  dirty: false,
  readOnly: false,
  degradeText: '报表设计器未就绪（占位）',
})

const emit = defineEmits<{
  change: [charts: ReportChartItem[]]
  select: [id: string | null]
  'add-chart': [payload: { datasetId: string; chartType: string }]
  'remove-chart': [id: string]
  save: []
  publish: []
  'save-as': []
  preview: []
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { options, load } = useBaseOptionSource<ReportDataset>({
  loader: async () => props.datasets.map((item) => ({ value: item, label: item.name })),
})
const selected = ref(props.selectedId)

watch(
  () => props.ready,
  (next) => {
    placeholder.setReady(next)
    if (next) {
      void load()
    }
  },
  { immediate: true },
)

watch(
  () => props.selectedId,
  (id) => {
    selected.value = id ?? ''
  },
)

/** 当前选中图表项。 */
const selectedChart = computed(() => props.charts.find((item) => item.id === selected.value))

/** 新增图表项（占位：点击数据集即加默认折线图）。 */
function addChart(dataset: ReportDataset): void {
  if (placeholder.disabled.value || props.readOnly || dataset.status !== 'enabled') {
    return
  }
  emit('add-chart', { datasetId: dataset.id, chartType: 'line' })
}

/** 画布选中联动配置面板。 */
function onSelect(id: string): void {
  selected.value = id
  emit('select', id)
}
</script>

<template>
  <div
    class="bms-report-designer"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-report-designer__toolbar" data-test="toolbar">
          <span data-test="report-code">{{ reportCode }}</span>
          <button type="button" data-test="save" :disabled="placeholder.disabled.value || readOnly" @click="emit('save')">保存</button>
          <button type="button" data-test="publish" :disabled="placeholder.disabled.value || readOnly" @click="emit('publish')">
            发布
          </button>
          <button type="button" data-test="save-as" :disabled="placeholder.disabled.value || readOnly" @click="emit('save-as')">
            另存为
          </button>
          <button type="button" data-test="preview" @click="emit('preview')">预览</button>
          <span v-if="dirty" data-test="dirty">未保存</span>
        </div>

        <div class="bms-report-designer__body">
          <div class="bms-report-designer__dataset" data-test="dataset-panel">
            <slot name="dataset-panel" :options="options">
              <button
                v-for="opt in options"
                :key="opt.value.id"
                type="button"
                :data-test="`dataset-${opt.value.id}`"
                :data-status="opt.value.status"
                :disabled="readOnly || opt.value.status !== 'enabled'"
                @click="addChart(opt.value)"
              >
                {{ opt.label }}
              </button>
            </slot>
          </div>

          <div class="bms-report-designer__canvas" data-test="canvas">
            <component
              :is="ReportCanvas"
              :charts="charts"
              :selected-id="selected"
              :read-only="readOnly"
              @select="onSelect"
              @remove-chart="emit('remove-chart', $event)"
            />
          </div>

          <div class="bms-report-designer__config" data-test="config-panel">
            <slot name="config-panel" :chart="selectedChart">
              <p v-if="selectedChart" data-test="config-selected">{{ selectedChart.chartType }}</p>
              <p v-else data-test="config-empty">未选中图表项</p>
            </slot>
          </div>
        </div>
      </slot>
    </template>
  </div>
</template>
