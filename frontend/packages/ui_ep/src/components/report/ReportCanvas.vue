<script setup lang="ts">
// 报表画布（08_09_01）：由 ReportDesigner 异步懒加载的独立分包入口；12 列网格承载图表卡（复用 07_06 ChartRenderer）。
import { computed, defineAsyncComponent, watch } from 'vue'

import { normalizeChartConfig, type ChartConfig, type ChartDatasetResult, type ReportChartItem, type ReportDataset } from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'
import ChartRenderer from '../chart/ChartRenderer.vue'

// 网格画布独立分包（gridstack 内核 08_09_01 接入）。
const ReportGrid = defineAsyncComponent(() => import('./ReportGrid.vue'))

interface Props {
  /** 图表项。 */
  charts?: ReportChartItem[]
  /** 当前选中标识。 */
  selectedId?: string
  /** 只读。 */
  readOnly?: boolean
  /** 数据集（脚注标注用）。 */
  datasets?: ReportDataset[]
  /** 各图表项数据（设计态预览取数结果，键为图表项标识）。 */
  chartData?: Record<string, ChartDatasetResult>
}

const props = withDefaults(defineProps<Props>(), {
  charts: () => [],
  selectedId: '',
  readOnly: false,
  datasets: () => [],
  chartData: () => ({}),
})

const emit = defineEmits<{
  select: [id: string]
  'remove-chart': [id: string]
  'duplicate-chart': [id: string]
  'center-chart': [id: string]
  'move-chart': [payload: { id: string; x: number; y: number }]
  'resize-chart': [payload: { id: string; w: number; h: number }]
}>()

const { state, setState } = useBaseDataState()

/**
 * 由图表项生成归一配置。
 *
 * @param item 图表项。
 * @returns 图表配置。
 */
function itemConfig(item: ReportChartItem): ChartConfig {
  const fields = props.datasets.find((dataset) => dataset.id === item.datasetId)?.fields ?? []
  const existing = item.config as unknown as Partial<ChartConfig> | undefined
  return normalizeChartConfig(
    {
      chartType: item.chartType,
      ...(item.title !== undefined ? { title: item.title } : {}),
      ...(existing ?? {}),
    },
    fields,
  )
}

/**
 * 数据集名称（脚注标注）。
 *
 * @param item 图表项。
 * @returns 数据集名称。
 */
function datasetName(item: ReportChartItem): string {
  return props.datasets.find((dataset) => dataset.id === item.datasetId)?.name ?? ''
}

const empty = computed(() => props.charts.length === 0)
watch(
  () => props.charts.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-report-canvas"
    data-test="report-canvas"
    data-subpackage="report"
    :data-state="state"
    :data-readonly="readOnly"
  >
    <p v-if="empty" data-test="canvas-empty">暂无图表（点击「添加图表」新建）</p>
    <ReportGrid
      v-else
      :charts="charts"
      :selected-id="selectedId"
      :read-only="readOnly"
      :datasets="datasets"
      @select="emit('select', $event)"
      @move-chart="emit('move-chart', $event)"
      @resize-chart="emit('resize-chart', $event)"
    >
      <template #default="{ item }">
        <div
          class="bms-report-canvas__card"
          :data-test="`chart-${item.id}`"
          :data-selected="item.id === selectedId || undefined"
          @click="emit('select', item.id)"
        >
          <div class="bms-report-canvas__head">
            <span>{{ item.title || `图表 ${item.id}` }}</span>
            <span class="bms-report-canvas__actions">
              <button type="button" :data-test="`chart-duplicate-${item.id}`" :disabled="readOnly" @click.stop="emit('duplicate-chart', item.id)">
                复制
              </button>
              <button type="button" :data-test="`chart-center-${item.id}`" :disabled="readOnly" @click.stop="emit('center-chart', item.id)">
                居中
              </button>
              <button type="button" :data-test="`remove-${item.id}`" :disabled="readOnly" @click.stop="emit('remove-chart', item.id)">
                删除
              </button>
            </span>
          </div>
          <div class="bms-report-canvas__body" :data-test="`chart-renderer-${item.id}`">
            <ChartRenderer :ready="true" :config="itemConfig(item)" :data="chartData[item.id]" :height="240" />
          </div>
          <p v-if="datasetName(item) !== ''" class="bms-report-canvas__footnote">{{ datasetName(item) }}</p>
        </div>
      </template>
    </ReportGrid>
  </div>
</template>

<style scoped>
.bms-report-canvas {
  width: 100%;
  min-height: 320px;
}
.bms-report-canvas__card {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bms-color-bg);
}
.bms-report-canvas__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  font-size: 13px;
}
.bms-report-canvas__footnote {
  margin: 0;
  padding: 2px 8px;
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}
</style>
