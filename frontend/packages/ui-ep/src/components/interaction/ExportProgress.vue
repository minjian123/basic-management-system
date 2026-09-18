<script setup lang="ts">
// 导出进度（占位，08_01_02）：由 ExportButton 异步懒加载的独立分包入口，真实实现（08_05）经 BaseAsyncTask 接异步导出。
import type { TaskProgress, TaskStatus } from '@bms/core'
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 任务状态。 */
  status?: TaskStatus
  /** 任务进度。 */
  progress?: TaskProgress | undefined
}

const props = withDefaults(defineProps<Props>(), {
  status: 'idle',
  progress: undefined,
})

const { state, setState } = useBaseDataState()
watch(
  () => props.status,
  (status) => {
    setState(status === 'running' ? 'loading' : status === 'error' ? 'error' : status === 'done' ? 'ready' : 'empty')
  },
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-export-progress"
    data-test="export-progress"
    data-subpackage="export"
    :data-status="status"
    :data-state="state"
  >
    <span data-test="export-status">{{ status }}</span>
    <span v-if="progress" data-test="export-percent">{{ progress.total ? `${progress.value}/${progress.total}` : progress.value }}</span>
  </div>
</template>
