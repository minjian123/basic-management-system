<script setup lang="ts">
// 大屏属性面板（08-9-2）：选中组件时的位置 / 尺寸 / 层级 / 类型 / 文案 / 数据源与样式；未选中时画布级配置。
import { computed } from 'vue'

import type { ReportDataset, ScreenCanvasConfig, ScreenComponent, ScreenComponentType } from '@bms/core'
import { SCREEN_COMPONENT_TYPES, componentLabel } from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 当前选中组件（缺省显示画布级配置）。 */
  component?: ScreenComponent
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 数据集清单。 */
  datasets?: ReportDataset[]
  /** 只读。 */
  readOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  component: undefined,
  canvas: undefined,
  datasets: () => [],
  readOnly: false,
})

const emit = defineEmits<{
  move: [payload: { id: string; x: number; y: number }]
  resize: [payload: { id: string; w: number; h: number }]
  reorder: [payload: { id: string; action: 'raise' | 'lower' | 'top' | 'bottom' }]
  update: [payload: { id: string; patch: { type?: ScreenComponentType; text?: string; datasetId?: string; chartType?: string } }]
  'canvas-update': [patch: Partial<ScreenCanvasConfig>]
}>()

const { setState } = useBaseDataState()
setState('ready')

/** 组件类型选项。 */
const typeOptions = computed(() => SCREEN_COMPONENT_TYPES.map((type) => ({ value: type, label: componentLabel(type) })))
/** 生效画布配置。 */
const canvasConfig = computed<ScreenCanvasConfig>(
  () => props.canvas ?? { width: 1920, height: 1080, theme: 'auto' },
)

/**
 * 读取数字输入值。
 *
 * @param event 事件。
 * @returns 数值（非法返回 `undefined`）。
 */
function numberValue(event: Event): number | undefined {
  const value = Number((event.target as HTMLInputElement).value)
  return Number.isFinite(value) ? Math.round(value) : undefined
}

/**
 * 处理位置输入。
 *
 * @param field 字段。
 * @param event 事件。
 */
function onPosition(field: 'x' | 'y', event: Event): void {
  const item = props.component
  const value = numberValue(event)
  if (item === undefined || value === undefined) {
    return
  }
  emit('move', { id: item.id, x: field === 'x' ? value : item.x, y: field === 'y' ? value : item.y })
}

/**
 * 处理尺寸输入。
 *
 * @param field 字段。
 * @param event 事件。
 */
function onSize(field: 'w' | 'h', event: Event): void {
  const item = props.component
  const value = numberValue(event)
  if (item === undefined || value === undefined) {
    return
  }
  emit('resize', { id: item.id, w: field === 'w' ? value : item.w, h: field === 'h' ? value : item.h })
}

/**
 * 处理类型选择。
 *
 * @param event 事件。
 */
function onType(event: Event): void {
  const item = props.component
  if (item === undefined) {
    return
  }
  emit('update', { id: item.id, patch: { type: (event.target as HTMLSelectElement).value as ScreenComponentType } })
}

/**
 * 处理文案输入。
 *
 * @param event 事件。
 */
function onText(event: Event): void {
  const item = props.component
  if (item === undefined) {
    return
  }
  emit('update', { id: item.id, patch: { text: (event.target as HTMLInputElement).value } })
}

/**
 * 处理数据集选择。
 *
 * @param event 事件。
 */
function onDataset(event: Event): void {
  const item = props.component
  if (item === undefined) {
    return
  }
  emit('update', { id: item.id, patch: { datasetId: (event.target as HTMLSelectElement).value } })
}

/**
 * 处理图表类型输入。
 *
 * @param event 事件。
 */
function onChartType(event: Event): void {
  const item = props.component
  if (item === undefined) {
    return
  }
  emit('update', { id: item.id, patch: { chartType: (event.target as HTMLInputElement).value } })
}

/**
 * 处理画布分辨率。
 *
 * @param field 字段。
 * @param event 事件。
 */
function onResolution(field: 'width' | 'height', event: Event): void {
  const value = numberValue(event)
  if (value === undefined) {
    return
  }
  emit('canvas-update', { [field]: value })
}

/**
 * 处理画布主题。
 *
 * @param event 事件。
 */
function onTheme(event: Event): void {
  emit('canvas-update', { theme: (event.target as HTMLSelectElement).value as ScreenCanvasConfig['theme'] })
}

/**
 * 处理画布背景色。
 *
 * @param event 事件。
 */
function onBackground(event: Event): void {
  emit('canvas-update', { background: { color: (event.target as HTMLInputElement).value } })
}
</script>

<template>
  <div class="bms-screen-property" data-test="property-panel-detail">
    <template v-if="component">
      <div class="bms-screen-property__row">
        <label>x <input :data-test="'prop-x'" type="number" :value="component.x" :disabled="readOnly" @change="onPosition('x', $event)" /></label>
        <label>y <input :data-test="'prop-y'" type="number" :value="component.y" :disabled="readOnly" @change="onPosition('y', $event)" /></label>
      </div>
      <div class="bms-screen-property__row">
        <label>宽 <input :data-test="'prop-w'" type="number" :value="component.w" :disabled="readOnly" @change="onSize('w', $event)" /></label>
        <label>高 <input :data-test="'prop-h'" type="number" :value="component.h" :disabled="readOnly" @change="onSize('h', $event)" /></label>
      </div>
      <div class="bms-screen-property__row">
        <span data-test="prop-z">层级 {{ component.z }}</span>
        <button type="button" data-test="prop-raise" :disabled="readOnly" @click="emit('reorder', { id: component.id, action: 'raise' })">上移</button>
        <button type="button" data-test="prop-lower" :disabled="readOnly" @click="emit('reorder', { id: component.id, action: 'lower' })">下移</button>
        <button type="button" data-test="prop-top" :disabled="readOnly" @click="emit('reorder', { id: component.id, action: 'top' })">置顶</button>
        <button type="button" data-test="prop-bottom" :disabled="readOnly" @click="emit('reorder', { id: component.id, action: 'bottom' })">置底</button>
      </div>
      <label class="bms-screen-property__field"
        >类型
        <select data-test="prop-type" :value="component.type" :disabled="readOnly" @change="onType">
          <option v-for="option in typeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <label class="bms-screen-property__field">文案 <input data-test="prop-text" type="text" :value="component.text ?? ''" :disabled="readOnly" @change="onText" /></label>
      <label class="bms-screen-property__field"
        >数据集
        <select data-test="prop-dataset" :value="component.datasetId ?? ''" :disabled="readOnly" @change="onDataset">
          <option value="">（无）</option>
          <option v-for="dataset in datasets" :key="dataset.id" :value="dataset.id" :disabled="dataset.status !== 'enabled'">{{ dataset.name }}</option>
        </select>
      </label>
      <label class="bms-screen-property__field">图表类型 <input data-test="prop-chart-type" type="text" :value="component.chartType ?? ''" :disabled="readOnly" @change="onChartType" /></label>
    </template>
    <template v-else>
      <label class="bms-screen-property__field">分辨率 <input data-test="prop-resolution" type="number" :value="canvasConfig.width" :disabled="readOnly" @change="onResolution('width', $event)" /> × <input data-test="prop-resolution-height" type="number" :value="canvasConfig.height" :disabled="readOnly" @change="onResolution('height', $event)" /></label>
      <label class="bms-screen-property__field">背景 <input data-test="prop-background" type="color" :value="canvasConfig.background?.color ?? '#ffffff'" @change="onBackground" /></label>
      <label class="bms-screen-property__field"
        >主题
        <select data-test="prop-theme" :value="canvasConfig.theme ?? 'auto'" :disabled="readOnly" @change="onTheme">
          <option value="auto">跟随</option>
          <option value="light">浅色</option>
          <option value="dark">深色</option>
        </select>
      </label>
    </template>
  </div>
</template>

<style scoped>
.bms-screen-property {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}
.bms-screen-property__row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bms-screen-property__field {
  display: flex;
  align-items: center;
  gap: 6px;
}
.bms-screen-property input[type='number'] {
  width: 72px;
}
</style>
