<script setup lang="ts">
// 报表画布（占位，08_01_03）：由 ReportDesigner 异步懒加载的独立分包入口，真实实现（08_09）承载 12 列网格与图表渲染。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { ReportChartItem } from './ReportDesigner.vue'

interface Props {
  /** 图表项。 */
  charts?: ReportChartItem[]
  /** 当前选中图表项标识。 */
  selectedId?: string
  /** 只读。 */
  readOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  charts: () => [],
  selectedId: '',
  readOnly: false,
})

const emit = defineEmits<{
  select: [id: string]
  'remove-chart': [id: string]
}>()

const { state, setState } = useBaseDataState()
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
    <p v-if="charts.length === 0" data-test="canvas-empty">暂无图表（占位，真实实现支持网格拖拽排版）</p>
    <div
      v-for="item in charts"
      :key="item.id"
      class="bms-report-canvas__card"
      :data-test="`chart-${item.id}`"
      :data-selected="item.id === selectedId || undefined"
      @click="emit('select', item.id)"
    >
      <span>{{ item.title || item.chartType }}</span>
      <button type="button" :data-test="`remove-${item.id}`" :disabled="readOnly" @click.stop="emit('remove-chart', item.id)">
        删除
      </button>
    </div>
  </div>
</template>
