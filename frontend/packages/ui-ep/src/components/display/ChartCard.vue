<script setup lang="ts">
// 图表卡（占位版，07_01）：契约先行冻结；数据通路未就绪时不请求、降级提示。
import { watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'

/** 图表类型。 */
export type ChartType = 'line' | 'bar' | 'pie' | 'area' | 'scatter' | 'map'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 卡标题。 */
  title?: string
  /** 图表类型。 */
  chartType?: ChartType
  /** 图表配置（ECharts option）。 */
  option?: Record<string, unknown>
  /** 加载中。 */
  loading?: boolean
  /** 卡片高度（px）。 */
  height?: number
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  title: '',
  chartType: 'line',
  option: undefined,
  loading: false,
  height: 300,
  degradeText: '图表数据未就绪（占位）',
})

const emit = defineEmits<{
  refresh: []
  'chart-click': [params: Record<string, unknown>]
  download: []
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)
</script>

<template>
  <div class="bms-chart-card" :data-ready="placeholder.ready.value" :data-degraded="placeholder.degraded.value">
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-chart-card__header" data-test="header">
        <span class="bms-chart-card__title" data-test="title">{{ title }}</span>
        <div class="bms-chart-card__actions">
          <slot name="actions" />
          <button type="button" data-test="refresh" @click="emit('refresh')">刷新</button>
          <button type="button" data-test="download" @click="emit('download')">导出</button>
        </div>
      </div>
      <div
        class="bms-chart-card__body"
        :style="{ height: `${height}px` }"
        :data-chart-type="chartType"
        data-test="chart"
        @click="emit('chart-click', { chartType, option })"
      >
        <slot name="live" :chart-type="chartType" :option="option">
          <span data-test="chart-holder">图表（{{ chartType }}）</span>
        </slot>
      </div>
    </template>
  </div>
</template>
