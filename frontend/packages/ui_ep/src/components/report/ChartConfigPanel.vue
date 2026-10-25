<script setup lang="ts">
// 图表配置面板（08_09_01）：图表类型 / 标题 / 维度·度量·系列映射 / 常用样式 / 高级配置覆盖。
import { computed, ref, watch } from 'vue'

import {
  CHART_KINDS,
  normalizeChartConfig,
  type ChartConfig,
  type ReportChartItem,
  type ReportField,
} from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 当前图表项。 */
  item?: ReportChartItem
  /** 当前数据集字段。 */
  fields?: ReportField[]
  /** 只读。 */
  readOnly?: boolean
  /** 占位禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  item: undefined,
  fields: () => [],
  readOnly: false,
  disabled: false,
})

const emit = defineEmits<{
  update: [payload: { patch: { title?: string; chartType?: string; config?: Record<string, unknown> } }]
  'preview-data': [payload: { chartId: string }]
}>()

/** 高级配置文本。 */
const overrideText = ref('')
/** 高级配置错误。 */
const overrideError = ref('')

/** 数据状态（空 / 就绪）。 */
const { state, setState } = useBaseDataState()
watch(
  () => props.item,
  (item) => setState(item !== undefined ? 'ready' : 'empty'),
  { immediate: true },
)

/** 当前配置。 */
const config = computed<ChartConfig>(() => {
  const item = props.item
  if (item === undefined) {
    return normalizeChartConfig({ chartType: 'line' })
  }
  const existing = item.config as unknown as Partial<ChartConfig> | undefined
  return normalizeChartConfig(
    { chartType: item.chartType, ...(item.title !== undefined ? { title: item.title } : {}), ...(existing ?? {}) },
    props.fields,
  )
})

watch(
  () => props.item?.id,
  () => {
    overrideText.value = config.value.override !== undefined ? JSON.stringify(config.value.override) : ''
    overrideError.value = ''
  },
  { immediate: true },
)

/**
 * 提交配置变更。
 *
 * @param partial 变更片段。
 */
function patch(partial: Partial<ChartConfig>): void {
  if (props.readOnly || props.disabled || props.item === undefined) {
    return
  }
  const next: ChartConfig = { ...config.value, ...partial }
  emit('update', { patch: { config: next as unknown as Record<string, unknown> } })
}

/**
 * 切换图表类型。
 *
 * @param value 类型。
 */
function onKind(value: string): void {
  if (props.readOnly || props.disabled || props.item === undefined) {
    return
  }
  const next: ChartConfig = { ...config.value, chartType: value as ChartConfig['chartType'] }
  emit('update', { patch: { chartType: value, config: next as unknown as Record<string, unknown> } })
}

/**
 * 改标题。
 *
 * @param value 标题。
 */
function onTitle(value: string): void {
  if (props.readOnly || props.disabled || props.item === undefined) {
    return
  }
  emit('update', { patch: { title: value } })
}

/**
 * 改映射字段。
 *
 * @param key 映射键。
 * @param value 值。
 */
function onMapping(key: 'dimension' | 'series' | 'metrics', value: string | string[]): void {
  const mapping = { ...config.value.mapping }
  if (key === 'metrics') {
    mapping.metrics = Array.isArray(value) ? value : [value]
  } else if (value === '') {
    delete mapping[key]
  } else {
    mapping[key] = value as string
  }
  patch({ mapping })
}

/**
 * 改常用样式。
 *
 * @param key 样式键。
 * @param value 值。
 */
function onStyle(key: keyof NonNullable<ChartConfig['style']>, value: unknown): void {
  patch({ style: { ...(config.value.style ?? {}), [key]: value } })
}

/** 应用高级配置覆盖。 */
function applyOverride(): void {
  const text = overrideText.value.trim()
  if (text === '') {
    patch({ override: undefined })
    overrideError.value = ''
    return
  }
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>
    patch({ override: parsed })
    overrideError.value = ''
  } catch {
    overrideError.value = '高级配置需为合法 JSON'
  }
}
</script>

<template>
  <div class="bms-report-config" data-test="chart-config-panel" :data-state="state" :data-readonly="readOnly || disabled">
    <p v-if="item === undefined" data-test="config-empty">未选中图表：点击画布中的图表卡编辑配置。</p>
    <template v-else>
      <p data-test="config-selected">{{ item.chartType }}</p>
      <label>
        图表类型
        <select data-test="config-type" :disabled="readOnly || disabled" :value="config.chartType" @change="onKind(($event.target as HTMLSelectElement).value)">
          <option v-for="kind in CHART_KINDS" :key="kind.kind" :value="kind.kind">{{ kind.label }}</option>
        </select>
      </label>
      <label>
        标题
        <input data-test="config-title" :disabled="readOnly || disabled" :value="item.title ?? ''" @input="onTitle(($event.target as HTMLInputElement).value)" />
      </label>
      <label>
        维度
        <select data-test="config-dimension" :disabled="readOnly || disabled" :value="config.mapping.dimension ?? ''" @change="onMapping('dimension', ($event.target as HTMLSelectElement).value)">
          <option value="">（无）</option>
          <option v-for="field in fields" :key="field.name" :value="field.name">{{ field.name }}</option>
        </select>
      </label>
      <label>
        度量（多选）
        <select
          multiple
          data-test="config-metrics"
          :disabled="readOnly || disabled"
          :value="config.mapping.metrics"
          @change="onMapping('metrics', Array.from(($event.target as HTMLSelectElement).selectedOptions).map((option) => option.value))"
        >
          <option v-for="field in fields" :key="field.name" :value="field.name">{{ field.name }}</option>
        </select>
      </label>
      <label>
        系列
        <select data-test="config-series" :disabled="readOnly || disabled" :value="config.mapping.series ?? ''" @change="onMapping('series', ($event.target as HTMLSelectElement).value)">
          <option value="">（无）</option>
          <option v-for="field in fields" :key="field.name" :value="field.name">{{ field.name }}</option>
        </select>
      </label>
      <label>
        图例
        <input type="checkbox" data-test="config-legend" :disabled="readOnly || disabled" :checked="config.style?.legend ?? true" @change="onStyle('legend', ($event.target as HTMLInputElement).checked)" />
      </label>
      <label>
        坐标轴名称
        <input data-test="config-axis-name" :disabled="readOnly || disabled" :value="config.style?.axisName ?? ''" @input="onStyle('axisName', ($event.target as HTMLInputElement).value)" />
      </label>
      <label>
        平滑
        <input type="checkbox" data-test="config-smooth" :disabled="readOnly || disabled" :checked="config.style?.smooth ?? false" @change="onStyle('smooth', ($event.target as HTMLInputElement).checked)" />
      </label>
      <label>
        堆叠
        <input type="checkbox" data-test="config-stacked" :disabled="readOnly || disabled" :checked="config.style?.stacked ?? false" @change="onStyle('stacked', ($event.target as HTMLInputElement).checked)" />
      </label>
      <label>
        数据标注
        <input type="checkbox" data-test="config-label" :disabled="readOnly || disabled" :checked="config.style?.label ?? false" @change="onStyle('label', ($event.target as HTMLInputElement).checked)" />
      </label>
      <label>
        色板序号
        <input type="number" data-test="config-palette" :disabled="readOnly || disabled" :value="config.style?.paletteIndex ?? 0" @input="onStyle('paletteIndex', Number(($event.target as HTMLInputElement).value))" />
      </label>
      <label>
        高级配置（JSON）
        <textarea data-test="config-override" :disabled="readOnly || disabled" :value="overrideText" @input="overrideText = ($event.target as HTMLTextAreaElement).value" @change="applyOverride" />
      </label>
      <p v-if="overrideError !== ''" data-test="config-error">{{ overrideError }}</p>
      <button type="button" data-test="config-preview" :disabled="readOnly || disabled" @click="emit('preview-data', { chartId: item.id })">
        预览数据
      </button>
    </template>
  </div>
</template>

<style scoped>
.bms-report-config {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  font-size: 13px;
}
.bms-report-config label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
