<script setup lang="ts">
// 导出触发（占位版，08_01_02）：契约先行冻结；数据通路未就绪时不请求、按钮禁用 + 降级提示。异步进度独立分包懒加载。
import { computed, defineAsyncComponent, watch } from 'vue'

import { useBaseAsyncTask } from '../../composables/useBaseAsyncTask'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 异步导出进度独立分包（真实实现 08_05 经 BaseAsyncTask 接入）。
const ExportProgress = defineAsyncComponent(() => import('./ExportProgress.vue'))

/** 导出范围。 */
export type ExportScope = 'filtered' | 'selected'

/** 导出载荷。 */
export interface ExportPayload {
  /** 业务标识。 */
  biz: string
  /** 导出范围。 */
  scope: ExportScope
  /** 当前筛选与排序参数。 */
  params: Record<string, unknown> | undefined
  /** 选中行标识（选中导出）。 */
  selectedIds: string[] | undefined
  /** 是否明文导出（`data:plain`）。 */
  plain: boolean
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 业务标识。 */
  biz?: string
  /** 业务中文名（文件名前缀缺省取此值）。 */
  bizName?: string
  /** 当前筛选与排序参数。 */
  params?: Record<string, unknown>
  /** 选中行标识。 */
  selectedIds?: string[]
  /** 导出范围。 */
  scope?: ExportScope
  /** 文件名前缀。 */
  filenamePrefix?: string
  /** 异步阈值（0 = 前端不判断）。 */
  asyncThreshold?: number
  /** 当前筛选总条数。 */
  total?: number
  /** 是否明文导出。 */
  plain?: boolean
  /** 外部禁用。 */
  disabled?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  biz: '',
  bizName: '',
  params: undefined,
  selectedIds: undefined,
  scope: 'filtered',
  filenamePrefix: '',
  asyncThreshold: 0,
  total: 0,
  plain: false,
  disabled: false,
  degradeText: '导出未就绪（占位）',
})

const emit = defineEmits<{
  export: [payload: ExportPayload]
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { status, progress } = useBaseAsyncTask<unknown>()

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

/** 是否禁用（占位 / 外部禁用 / 选中导出未选行）。 */
const exportDisabled = computed(
  () =>
    placeholder.disabled.value ||
    props.disabled ||
    (props.scope === 'selected' && (props.selectedIds?.length ?? 0) === 0),
)

/** 触发导出（占位：仅透传事件）。 */
function doExport(): void {
  if (exportDisabled.value) {
    return
  }
  emit('export', {
    biz: props.biz,
    scope: props.scope,
    params: props.params,
    selectedIds: props.selectedIds,
    plain: props.plain,
  })
}
</script>

<template>
  <div
    class="bms-export-button"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <button type="button" data-test="export" disabled>导出</button>
      <span class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</span>
    </slot>
    <template v-else>
      <slot name="live">
        <span data-test="total-hint">导出 {{ total }} 条</span>
        <button type="button" data-test="export" :disabled="exportDisabled" @click="doExport">
          <slot name="default">导出</slot>
        </button>
        <span v-if="!plain" data-test="plain-hint">敏感字段将脱敏导出</span>
        <component :is="ExportProgress" :status="status" :progress="progress" />
      </slot>
    </template>
  </div>
</template>
