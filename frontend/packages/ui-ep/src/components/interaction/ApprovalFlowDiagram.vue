<script setup lang="ts">
// 审批流只读 BPMN 图（占位，08_01_01）：由 ApprovalFlow 异步懒加载的独立分包入口，真实实现（08_08）换 bpmn-js Viewer。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** BPMN 定义快照 XML（只读图数据源）。 */
  xml?: string
  /** 高亮当前节点 id。 */
  currentNodeId?: string
}

const props = withDefaults(defineProps<Props>(), {
  xml: '',
  currentNodeId: '',
})

const { state, setState } = useBaseDataState()
watch(
  () => props.xml,
  (xml) => setState(xml ? 'ready' : 'empty'),
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-flow-diagram"
    data-test="bpmn-diagram"
    data-subpackage="bpmn"
    :data-state="state"
    :data-node="currentNodeId || undefined"
  >
    <div class="bms-flow-diagram__note" data-test="diagram-note">流程只读图（占位，待 bpmn-js 接入）</div>
  </div>
</template>
