<script setup lang="ts">
// 导出触发（08_05）：按当前筛选 / 选中行取数与超阈值异步导出反馈、脱敏提示与动作权限显隐。
// 对外契约保持 08_01_02 冻结形状（导出名 / 既有 Props / 事件 / data-test 不变），仅向后兼容新增可选 Props 与事件。
// 事件与注入双轨：点击一律保留既有事件上抛；仅当宿主注入 jobs 时件内才驱动真实编排（二选一，避免重复执行）。
import {
  EXPORT_PERM,
  EXPORT_PLACEHOLDER_TEXT,
  type BaseAccess,
  type BaseAsyncTask,
  type BaseNotice,
  type BaseFileDownload,
  type ExportJobs,
  type ExportResult,
  type ExportScope,
  type TaskProgress,
} from '@bms/core'
import { computed, defineAsyncComponent, watch } from 'vue'

import { useBaseExportFlow } from '../../composables/useBaseExportFlow'

// 异步导出进度独立分包（`defineAsyncComponent`；不在宿主静态 import 中）。
const ExportProgress = defineAsyncComponent(() => import('./ExportProgress.vue'))

export type { ExportScope }

/** 导出载荷（既有对外形状，保持不变）。 */
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
  /** 注入的处理函数集（未注入即仅事件上抛）。 */
  jobs?: ExportJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 异步任务能力（后台导出经其 poller 两段）。 */
  task?: BaseAsyncTask<ExportResult>
  /** 下载触发能力（结果下载经其触发）。 */
  download?: BaseFileDownload
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
  degradeText: EXPORT_PLACEHOLDER_TEXT,
  jobs: undefined,
  access: undefined,
  notice: undefined,
  task: undefined,
  download: undefined,
})

const emit = defineEmits<{
  export: [payload: ExportPayload]
  retry: []
  exported: [result: ExportResult]
  queued: [result: ExportResult]
  failed: [payload: { message: string }]
  progress: [progress: TaskProgress]
}>()

const flow = useBaseExportFlow({
  ready: props.ready,
  biz: props.biz,
  bizName: props.bizName,
  params: props.params,
  selectedIds: props.selectedIds,
  scope: props.scope,
  asyncThreshold: props.asyncThreshold,
  total: props.total,
  plain: props.plain,
  filenamePrefix: props.filenamePrefix,
  disabled: props.disabled,
  jobs: props.jobs,
  task: props.task,
  download: props.download,
  access: props.access,
  notice: props.notice,
})

/** 是否由件内驱动真实编排（宿主注入导出处理函数时为真）。 */
function inline(): boolean {
  return flow.flow.jobs.export !== undefined
}

watch(
  () => props.ready,
  (value) => flow.setReady(value),
)
watch(
  () => props.jobs,
  (value) => {
    if (value !== undefined) {
      flow.setJobs(value)
    }
  },
)
watch(
  () => props.params,
  (value) => flow.setParams(value),
)
watch(
  () => [props.biz, props.bizName] as const,
  ([biz, bizName]) => {
    if (biz !== undefined) {
      flow.setBiz(biz, bizName)
    }
  },
)
watch(
  () => [props.scope, props.selectedIds] as const,
  ([scope, selectedIds]) => flow.setScope(scope, selectedIds),
)
watch(
  () => props.total,
  (value) => flow.setTotal(value),
)
watch(
  () => props.plain,
  (value) => flow.setPlain(value),
)
watch(
  () => props.asyncThreshold,
  (value) => flow.setThreshold(value),
)
watch(
  () => props.disabled,
  (value) => flow.setDisabled(value),
)
watch(
  () => [props.filenamePrefix, props.bizName] as const,
  ([prefix, bizName]) => {
    if (prefix !== undefined) {
      flow.flow.filenamePrefix = prefix
      flow.setBiz(props.biz, bizName)
    }
  },
)

/** 是否具备导出权限（权限上下文未注入视为有权，后端兜底）。 */
const permAllowed = computed(() => {
  const access = flow.flow.access
  return access === undefined || access.has(EXPORT_PERM)
})

/**
 * 是否禁用（占位 / 外部禁用 / 无权 / 选中导出未选行 / 进行中）。
 *
 * **无数据不预先禁用**：`total` 缺省 0 无法区分「宿主未传」与「真无数据」，故入口不做无数据禁用，
 * 点击后由核心写「当前筛选无数据可导出」提示且不发请求（零请求）；此口径同时保持 `08_01_02` 冻结的既有断言
 * （就绪态点击必上抛 `export`）。核心 `canExport` 仍含无数据分支，作为内部决策守卫。
 */
const exportDisabled = computed(
  () =>
    flow.degraded.value ||
    props.disabled ||
    flow.busy.value ||
    !permAllowed.value ||
    (props.scope === 'selected' && (props.selectedIds?.length ?? 0) === 0),
)

/** 触发导出（先上抛既有事件；注入处理函数时驱动真实编排）。 */
async function doExport(): Promise<void> {
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
  if (!inline()) {
    return
  }
  const result = await flow.run()
  if (result !== undefined) {
    emit('exported', result)
    if (result.async === true) {
      emit('queued', result)
    }
    return
  }
  if (flow.phase.value === 'failed') {
    emit('failed', { message: flow.flow.errorMessage })
  }
}

watch(flow.progress, (value) => emit('progress', { ...value }))

defineExpose({ flow: flow.flow })
</script>

<template>
  <div class="bms-export-button" :data-ready="flow.ready.value" :data-degraded="flow.degraded.value">
    <slot v-if="flow.degraded.value" name="degrade">
      <button type="button" data-test="export" disabled>导出</button>
      <span class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</span>
    </slot>
    <template v-else>
      <slot name="live">
        <span data-test="total-hint">导出 {{ total }} 条</span>
        <button type="button" data-test="export" :disabled="exportDisabled" @click="doExport">
          <slot name="default">导出</slot>
        </button>
        <span v-if="!flow.plainAllowed.value" data-test="plain-hint">
          {{ plain ? '未持明文权限，敏感字段将脱敏导出' : '敏感字段将脱敏导出' }}
        </span>
        <span v-if="flow.asyncMode.value" data-test="async-hint">
          {{ flow.empty.value ? '当前筛选无数据可导出' : '数据量较大，将转后台导出' }}
        </span>
        <component
          :is="ExportProgress"
          :status="flow.flow.task?.status ?? 'idle'"
          :progress="flow.progress.value"
          :phase="flow.phase.value"
          @cancel="flow.cancel()"
          @retry="flow.retry()"
        />
      </slot>
    </template>
  </div>
</template>
