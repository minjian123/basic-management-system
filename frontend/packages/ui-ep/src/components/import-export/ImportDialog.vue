<script setup lang="ts">
// 导入对话框（08_05）：三步导入真实编排（模板下载 / 文件校验与幂等键 / 上传解析 / 结果与错误行报告）。
// 对外契约保持 08_01_02 冻结形状（导出名 / 既有 Props / 事件 / data-test 不变），仅向后兼容新增可选 Props 与事件。
// 事件与注入双轨：点击一律保留既有事件上抛；仅当宿主注入 jobs 时件内才驱动真实编排（二选一，避免重复执行）。
import {
  IMPORT_PLACEHOLDER_TEXT,
  type BaseAccess,
  type BaseNotice,
  type ImportJobs,
  type ImportResult,
  type ImportStep,
} from '@bms/core'
import { computed, defineAsyncComponent, watch } from 'vue'

import { useBaseFileDownload } from '../../composables/useBaseFileDownload'
import { useBaseImportFlow } from '../../composables/useBaseImportFlow'
import { useBaseUploadEngine } from '../../composables/useBaseUploadEngine'
import { triggerDownload } from '../../utils/downloadFile'

// 导入主体独立分包（`defineAsyncComponent`；不在宿主静态 import 中）。
const ImportDialogBody = defineAsyncComponent(() => import('./ImportDialogBody.vue'))

export type { ImportResult, ImportStep }

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 对话框显隐。 */
  visible?: boolean
  /** 业务标识（后端路径段）。 */
  biz?: string
  /** 业务中文名（标题与错误明细文件名）。 */
  bizName?: string
  /** 接受的文件类型。 */
  accept?: string
  /** 文件大小上限（字节；0 表示不限）。 */
  maxSize?: number
  /** 模板下载参数。 */
  templateParams?: Record<string, unknown>
  /** 全部成功后是否自动关闭。 */
  successAutoClose?: boolean
  /** 错误行每页行数（缺省 20）。 */
  errorPageSize?: number
  /** 降级文案。 */
  degradeText?: string
  /** 注入的处理函数集（未注入即仅事件上抛）。 */
  jobs?: ImportJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  visible: false,
  biz: '',
  bizName: '',
  accept: '.xlsx',
  maxSize: 20 * 1024 * 1024,
  templateParams: undefined,
  successAutoClose: false,
  errorPageSize: 20,
  degradeText: IMPORT_PLACEHOLDER_TEXT,
  jobs: undefined,
  access: undefined,
  notice: undefined,
})

const emit = defineEmits<{
  'update:visible': [visible: boolean]
  'download-template': [params: Record<string, unknown> | undefined]
  submit: [payload: { file: File; idempotencyKey: string }]
  retry: []
  'download-errors': []
  done: []
  reset: []
  imported: [result: ImportResult]
  failed: [payload: { message: string }]
}>()

/** 下载触发（件层工具注入；宿主可覆盖）。 */
const download = useBaseFileDownload({ trigger: triggerDownload })
/** 上传引擎（进度与取消由其承载）。 */
const upload = useBaseUploadEngine<unknown>({ maxSize: props.maxSize })

const flow = useBaseImportFlow({
  ready: props.ready,
  biz: props.biz,
  bizName: props.bizName,
  accept: props.accept,
  maxSize: props.maxSize,
  templateParams: props.templateParams,
  successAutoClose: props.successAutoClose,
  jobs: props.jobs,
  engine: upload.engine,
  download: download.download,
  access: props.access,
  notice: props.notice,
})

/** 是否由件内驱动真实编排（宿主注入执行处理函数时为真）。 */
function inline(): boolean {
  return flow.flow.jobs.execute !== undefined
}

/** 生效阶段（用于重试入口显隐）。 */
const failed = computed(() => flow.phase.value === 'failed')

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
  () => [props.biz, props.bizName] as const,
  ([biz, bizName]) => {
    if (biz !== undefined) {
      flow.setBiz(biz, bizName)
    }
  },
)
watch(
  () => props.visible,
  (value) => {
    if (!value) {
      flow.reset()
    }
  },
)

/** 提交是否禁用（占位 / 未选文件 / 文件校验失败 / 进行中 / 无权）。 */
const submitDisabled = computed(
  () => flow.degraded.value || !flow.hasFile.value || flow.fileError.value !== '' || !flow.canImport.value,
)
/** 关闭是否禁用（上传 / 解析中禁止关闭）。 */
const closeDisabled = computed(() => flow.degraded.value || flow.busy.value)

/** 选择文件（映射元信息后交核心校验）。 */
function pickFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0]
  if (picked !== undefined && picked !== null) {
    flow.selectFile(picked, { name: picked.name, size: picked.size, lastModified: picked.lastModified })
  }
}

/** 结果上抛（成功 → `imported` 与自动关闭；失败 → `failed`）。 */
function settle(result: ImportResult | undefined): void {
  if (result !== undefined) {
    emit('imported', result)
    if (props.successAutoClose && result.failCount === 0 && result.total > 0) {
      emit('update:visible', false)
      emit('done')
    }
    return
  }
  if (flow.phase.value === 'failed') {
    emit('failed', { message: flow.errorMessage.value })
  }
}

/** 提交导入（先上抛既有事件；注入处理函数时驱动真实编排）。 */
async function submit(): Promise<void> {
  if (submitDisabled.value) {
    return
  }
  const file = flow.flow.file
  if (!(file instanceof File)) {
    return
  }
  emit('submit', { file, idempotencyKey: flow.idempotencyKey.value })
  if (!inline()) {
    return
  }
  settle(await flow.submit())
}

/** 重新导入（回选文件步并重置，新一次导入）。 */
function reset(): void {
  flow.reset()
  emit('reset')
}

/** 重试失败导入（复用同一幂等键）。 */
async function retry(): Promise<void> {
  emit('retry')
  if (!inline()) {
    return
  }
  settle(await flow.retry())
}

/** 关闭对话框（上传 / 解析中禁止关闭）。 */
function close(): void {
  if (closeDisabled.value) {
    return
  }
  emit('update:visible', false)
}

/** 下载模板（先上抛既有事件；下载通路就绪时驱动真实取址与触发）。 */
async function downloadTemplate(): Promise<void> {
  emit('download-template', props.templateParams)
  if (flow.degraded.value) {
    return
  }
  await flow.downloadTemplate()
}

/** 下载错误明细（先上抛既有事件；下载通路就绪时驱动真实取址与触发）。 */
async function downloadErrors(): Promise<void> {
  emit('download-errors')
  if (flow.degraded.value) {
    return
  }
  await flow.downloadErrors()
}

defineExpose({ flow: flow.flow, download: download.download })
</script>

<template>
  <div class="bms-import-dialog" :data-ready="flow.ready.value" :data-degraded="flow.degraded.value">
    <slot v-if="flow.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <header class="bms-import-dialog__header" data-test="header">批量导入{{ bizName }}</header>
        <div class="bms-import-dialog__toolbar">
          <button type="button" data-test="template" :disabled="flow.degraded.value" @click="downloadTemplate">
            下载模板
          </button>
        </div>
        <input
          type="file"
          data-test="file-input"
          :accept="accept"
          :disabled="flow.degraded.value || flow.busy.value"
          @change="pickFile"
        />
        <span v-if="flow.fileMeta.value" data-test="file-name">{{ flow.fileMeta.value.name }}</span>
        <span v-if="flow.fileError.value" data-test="file-error">{{ flow.fileError.value }}</span>

        <component
          :is="ImportDialogBody"
          :step="flow.step.value"
          :phase="flow.phase.value"
          :progress="flow.progress.value"
          :result="flow.result.value"
          :error-message="flow.errorMessage.value"
          :error-page="flow.errorPage.value"
          :error-page-size="errorPageSize"
          :biz-name="bizName"
          :busy="flow.busy.value"
          @update:error-page="flow.setErrorPage($event)"
          @download-errors="downloadErrors"
        />

        <footer class="bms-import-dialog__footer" data-test="footer">
          <button type="button" data-test="submit" :disabled="submitDisabled" @click="submit">提交</button>
          <button type="button" data-test="retry" :disabled="flow.degraded.value || !failed" @click="retry">
            重试
          </button>
          <button
            type="button"
            data-test="download-errors"
            :disabled="flow.degraded.value || flow.result.value === undefined"
            @click="downloadErrors"
          >
            下载错误明细
          </button>
          <button type="button" data-test="reset" :disabled="flow.busy.value" @click="reset">重新导入</button>
          <button type="button" data-test="close" :disabled="closeDisabled" @click="close">关闭</button>
        </footer>
      </slot>
    </template>
  </div>
</template>
