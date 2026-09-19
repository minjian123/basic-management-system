<script setup lang="ts">
// 导出进度（08_05）：由 ExportButton 异步懒加载的独立分包入口，异步导出状态矩阵（idle / running / done / error / canceled）。
import type { ExportPhase, TaskProgress, TaskStatus } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 任务状态。 */
  status?: TaskStatus
  /** 任务进度。 */
  progress?: TaskProgress | undefined
  /** 导出阶段。 */
  phase?: ExportPhase
  /** 是否可取消（缺省 `true`）。 */
  cancellable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  status: 'idle',
  progress: undefined,
  phase: 'idle',
  cancellable: true,
})

const emit = defineEmits<{
  cancel: []
  retry: []
}>()

const { state, setState } = useBaseDataState()
watch(
  () => props.status,
  (status) => {
    setState(status === 'running' ? 'loading' : status === 'error' ? 'error' : status === 'done' ? 'ready' : 'empty')
  },
  { immediate: true },
)

/** 是否进行中（可取消）。 */
const running = computed(() => props.phase === 'exporting' || props.phase === 'queued' || props.status === 'running')
/** 进度文案（缺总量显示单项）。 */
const percentText = computed(() => {
  const progress = props.progress
  if (progress === undefined || progress === null) {
    return ''
  }
  return (progress.total ?? 0) > 0 ? `${progress.value}/${progress.total}` : `${progress.value}`
})
</script>

<template>
  <div
    class="bms-export-progress"
    data-test="export-progress"
    data-subpackage="export"
    :data-status="status"
    :data-state="state"
  >
    <span data-test="export-status">{{ phase !== 'idle' ? phase : status }}</span>
    <span v-if="progress" data-test="export-percent">{{ percentText }}</span>
    <button v-if="running && cancellable" type="button" data-test="export-cancel" @click="emit('cancel')">取消</button>
    <button v-if="phase === 'failed'" type="button" data-test="export-retry" @click="emit('retry')">重试</button>
  </div>
</template>
