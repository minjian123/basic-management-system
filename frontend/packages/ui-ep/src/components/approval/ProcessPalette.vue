<script setup lang="ts">
// 元素调板件（08_8_2）：仅列 BPMN 子集六类（对齐工作流引擎可解析范围）；点击或拖出即创建元素。
import { MODELER_SUBSET, type ModelerElementType } from '@bms/core'
import { computed } from 'vue'

import { useBaseProcessModeler } from '../../composables/useBaseProcessModeler'

interface Props {
  /** 元素清单（缺省 BPMN 子集）。 */
  elements?: readonly ModelerElementType[]
  /** 禁用（占位 / 只读）。 */
  disabled?: boolean
  /** 是否可拖拽。 */
  draggable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  elements: () => [...MODELER_SUBSET],
  disabled: false,
  draggable: true,
})

const emit = defineEmits<{
  add: [type: ModelerElementType]
  'drag-start': [type: ModelerElementType]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { modeler } = useBaseProcessModeler()

/** 元素中文名。 */
const LABELS: Readonly<Record<ModelerElementType, string>> = {
  startEvent: '开始事件',
  endEvent: '结束事件',
  userTask: '用户任务',
  exclusiveGateway: '排他网关',
  parallelGateway: '并行网关',
  sequenceFlow: '顺序流',
}

/** 展示项。 */
const items = computed(() => props.elements.map((type) => ({ type, label: LABELS[type] })))

/**
 * 拖出（数据载荷供画布落点使用）。
 *
 * @param event 拖拽事件。
 * @param type 元素类型。
 */
function onDragStart(event: DragEvent, type: ModelerElementType): void {
  if (props.disabled || !props.draggable) {
    event.preventDefault()
    return
  }
  event.dataTransfer?.setData('text/plain', type)
  emit('drag-start', type)
}

// 说明：`modeler` 仅为挂链（件层以投影组合式接入继承链）。
void modeler
</script>

<template>
  <div class="bms-process-palette" data-test="process-palette">
    <button
      v-for="item in items"
      :key="item.type"
      type="button"
      class="bms-process-palette__item"
      :data-test="`palette-${item.type}`"
      :draggable="draggable && !disabled"
      :disabled="disabled"
      @click="emit('add', item.type)"
      @dragstart="onDragStart($event, item.type)"
    >
      {{ item.label }}
    </button>
  </div>
</template>

<style scoped>
.bms-process-palette {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-process-palette__item {
  padding: 4px 8px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg, #ffffff);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.bms-process-palette__item:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
