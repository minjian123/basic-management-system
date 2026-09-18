<script setup lang="ts">
// 流程建模画布（占位，08_01_01）：由 ProcessModeler 异步懒加载的独立分包入口，真实实现（08_08）换 bpmn-js Modeler。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** BPMN XML。 */
  xml?: string
  /** 只读（历史版本 / 无 `wf:define`）。 */
  readOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  xml: '',
  readOnly: false,
})

const emit = defineEmits<{
  select: [element: { id: string; type: string; name?: string } | null]
  change: [xml: string]
}>()

const { state, setState } = useBaseDataState()
watch(
  () => props.xml,
  (xml) => setState(xml ? 'ready' : 'empty'),
  { immediate: true },
)

function onBlankClick(): void {
  emit('select', null)
}
</script>

<template>
  <div
    class="bms-process-canvas"
    data-test="process-canvas"
    data-subpackage="bpmn"
    :data-state="state"
    :data-readonly="readOnly"
    @click="onBlankClick"
  >
    <div class="bms-process-canvas__note" data-test="canvas-note">BPMN 建模画布（占位，待 bpmn-js 接入）</div>
  </div>
</template>
