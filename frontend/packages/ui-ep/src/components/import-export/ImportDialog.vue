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
import { ElButton, ElDialog, ElStep, ElSteps, ElUpload } from 'element-plus'
import type { UploadFile, UploadRawFile } from 'element-plus'
import { computed, defineAsyncComponent, ref, watch } from 'vue'

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

/** el-upload 受控文件列表（仅保留单个已选文件）。 */
const uploadFiles = ref<UploadFile[]>([])

/**
 * el-upload 选择变化（`auto-upload` 关闭，仅做选择与校验）。
 *
 * @param file 当前选中的上传文件。
 */
function onUploadChange(file: UploadFile): void {
  const raw = file.raw as UploadRawFile | undefined
  if (raw === undefined) {
    return
  }
  uploadFiles.value = [file]
  flow.selectFile(raw, { name: raw.name, size: raw.size, lastModified: raw.lastModified })
}

/** 移除已选文件（同步清空核心态与幂等键）。 */
function onUploadRemove(): void {
  uploadFiles.value = []
  flow.reset()
}

/**
 * 超出单文件上限时替换（节点 §3.3「更换文件视为新导入（新幂等键）」）。
 *
 * `el-upload` 在 `limit` 命中时不触发 `change`，故经 `on-exceed` 显式换文件，
 * 避免「再选一个文件却静默无反应」。
 *
 * @param files 本次新选的文件列表。
 */
function onUploadExceed(files: File[]): void {
  const raw = files[0]
  if (raw === undefined) {
    return
  }
  uploadFiles.value = [{ name: raw.name, size: raw.size, status: 'ready', uid: Date.now(), raw } as UploadFile]
  flow.selectFile(raw, { name: raw.name, size: raw.size, lastModified: raw.lastModified })
}

/**
 * 对话框显隐（受控双向绑定；上传 / 解析中禁止关闭）。
 */
const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => {
    if (!value && closeDisabled.value) {
      return
    }
    emit('update:visible', value)
  },
})

/**
 * 关闭前拦截（上传 / 解析中禁止关闭，节点 §3.6）。
 *
 * @param done 关闭回调（不允许关闭时不调用）。
 */
function beforeClose(done: () => void): void {
  if (closeDisabled.value) {
    return
  }
  done()
}

/** 三步步骤条当前步序（选文件 0 / 上传解析 1 / 结果 2）。 */
const stepIndex = computed(() => (flow.step.value === 'uploading' ? 1 : flow.step.value === 'result' ? 2 : 0))

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
        <el-dialog
          v-model="dialogVisible"
          class="bms-import-dialog__modal"
          :title="`批量导入${bizName}`"
          width="640px"
          :close-on-click-modal="false"
          :before-close="beforeClose"
          append-to-body
        >
          <div class="bms-import-dialog__steps" data-test="steps">
            <el-steps :active="stepIndex" simple>
              <el-step title="选文件" />
              <el-step title="上传解析" />
              <el-step title="结果" />
            </el-steps>
          </div>

          <div class="bms-import-dialog__toolbar" data-test="toolbar">
            <el-button :disabled="flow.degraded.value" data-test="template" @click="downloadTemplate">
              下载导入模板
            </el-button>
            <span class="bms-import-dialog__tip">按模板填写，列头不可增删；单次建议 ≤ 5000 行</span>
          </div>

          <el-upload
            v-model:file-list="uploadFiles"
            class="bms-import-dialog__upload"
            drag
            :auto-upload="false"
            :limit="1"
            :accept="accept"
            :disabled="flow.degraded.value || flow.busy.value"
            data-test="file-input"
            @change="onUploadChange"
            @remove="onUploadRemove"
            @exceed="onUploadExceed"
          >
            <div class="bms-import-dialog__drop">
              <div class="bms-import-dialog__drop-icon">⇪</div>
              <div>将 .xlsx 拖到此处，或 <em>点击选择文件</em></div>
              <div class="bms-import-dialog__tip">仅支持 {{ accept }}，单个文件 ≤ {{ Math.round(maxSize / 1024 / 1024) }}MB</div>
            </div>
          </el-upload>

          <p v-if="flow.fileMeta.value" class="bms-import-dialog__file" data-test="file-name">
            {{ flow.fileMeta.value.name }}
          </p>
          <p v-if="flow.fileError.value" class="bms-import-dialog__error" data-test="file-error">
            {{ flow.fileError.value }}
          </p>

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

          <template #footer>
            <div class="bms-import-dialog__footer" data-test="footer">
              <el-button
                type="primary"
                data-test="submit"
                :disabled="submitDisabled"
                :loading="flow.busy.value"
                @click="submit"
              >
                提交
              </el-button>
              <el-button data-test="retry" :disabled="flow.degraded.value || !failed" @click="retry">重试</el-button>
              <el-button
                data-test="download-errors"
                :disabled="flow.degraded.value || flow.result.value === undefined"
                @click="downloadErrors"
              >
                下载错误明细
              </el-button>
              <el-button data-test="reset" :disabled="flow.busy.value" @click="reset">重新导入</el-button>
              <el-button data-test="close" :disabled="closeDisabled" @click="close">关闭</el-button>
            </div>
          </template>
        </el-dialog>
      </slot>
    </template>
  </div>
</template>

<style scoped>
.bms-import-dialog {
  min-width: 0;
}

.bms-import-dialog__steps {
  margin-bottom: var(--bms-space-4);
}

.bms-import-dialog__steps :deep(.el-steps) {
  background: var(--bms-import-step-bg);
  border-radius: var(--bms-radius-sm);
}

/* 当前步字色取令牌（EP 内部字色不随 --bms-* 映射）。 */
.bms-import-dialog__steps :deep(.el-step__title.is-process),
.bms-import-dialog__steps :deep(.el-step__head.is-process) {
  color: var(--bms-import-step-active-color);
  border-color: var(--bms-import-step-active-color);
}

.bms-import-dialog__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-3);
  padding: var(--bms-space-2) var(--bms-space-3);
  background: var(--bms-color-fill);
  border-radius: var(--bms-radius-sm);
}

.bms-import-dialog__tip {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-import-dialog__upload {
  display: block;
  margin-top: var(--bms-space-3);
}

/* 拖拽区形态（原型：虚线框 + 图标 + 说明）。 */
.bms-import-dialog__upload :deep(.el-upload-dragger) {
  padding: var(--bms-space-6);
  background: var(--bms-import-drop-bg);
  border: 1px dashed var(--bms-import-drop-border);
  border-radius: var(--bms-radius-md);
}

.bms-import-dialog__upload :deep(.el-upload-dragger:hover),
.bms-import-dialog__upload :deep(.el-upload-dragger.is-dragover) {
  border-color: var(--bms-import-drop-active-border);
}

.bms-import-dialog__drop {
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
}

.bms-import-dialog__drop-icon {
  font-size: var(--bms-font-size-xl);
  line-height: var(--bms-line-height);
}

.bms-import-dialog__file {
  margin: var(--bms-space-2) 0 0;
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
}

.bms-import-dialog__error {
  margin: var(--bms-space-1) 0 0;
  color: var(--bms-field-error-color);
  font-size: var(--bms-font-size-xs);
}

.bms-import-dialog__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--bms-space-2);
}
</style>
