<script setup lang="ts">
// 文件上传字段（真实实现，06_07）：拖拽 / 进度 / 重试 / 取消 / 只读回显 / 下载预览。
// 对外契约保持 06_01 冻结形状（导出名 / 既有 Props / 事件 / 插槽 / data-test 不变），仅向后兼容新增可选 Props 与事件。
import {
  FILE_EMPTY_TEXT,
  FILE_PLACEHOLDER_TEXT,
  fileRefLabel,
  formatFileSize,
  isFileRefInvalid,
  isImageFile,
  type BaseFileDownload,
  type BasePresignedUrl,
  type FileRef,
  type UploadTransportAdapter,
} from '@bms/core'
import { computed, ref as vueRef, watch } from 'vue'

import { useBaseFileUpload } from '../../composables/useBaseFileUpload'
import FilePreview, { type PreviewFile } from '../display/FilePreview.vue'

/** 上传文件项（06_01 冻结契约）。 */
export interface UploadFieldItem {
  /** 唯一键。 */
  id: string
  /** 文件名。 */
  name: string
  /** 地址（回显）。 */
  url?: string
}

interface Props {
  /** 已上传文件（受控）。 */
  modelValue?: UploadFieldItem[]
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 数量上限。 */
  limit?: number
  /** 大小上限（MB）。 */
  maxSize?: number
  /** 接受类型。 */
  accept?: string
  /** 禁用。 */
  disabled?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 占位文案（新增）。 */
  placeholder?: string
  /** 是否多选（新增；缺省多选）。 */
  multiple?: boolean
  /** 上传通路（新增；未注入即占位零请求）。 */
  transport?: UploadTransportAdapter
  /** 预签名能力（新增）。 */
  presigned?: BasePresignedUrl
  /** 下载触发能力（新增）。 */
  download?: BaseFileDownload
  /** 分片大小（字节，新增）。 */
  partSize?: number
  /** 整包阈值（字节，新增）。 */
  wholeMaxSize?: number
  /** 分片并发（新增）。 */
  concurrency?: number
  /** 秒传开关（新增）。 */
  autoDedup?: boolean
  /** 多文件排序（新增）。 */
  draggable?: boolean
  /** 只读回显（新增）。 */
  readonly?: boolean
  /** 必填标记（新增）。 */
  required?: boolean
  /** 校验错误文案（新增）。 */
  errorMessage?: string
  /** 空态文案（新增）。 */
  emptyText?: string
  /** 显示进度（新增）。 */
  showProgress?: boolean
  /** 可下载（新增）。 */
  downloadable?: boolean
  /** 可预览（新增）。 */
  previewable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  ready: false,
  limit: undefined,
  maxSize: undefined,
  accept: '',
  disabled: false,
  degradeText: FILE_PLACEHOLDER_TEXT,
  placeholder: '点击或拖拽上传',
  multiple: true,
  transport: undefined,
  presigned: undefined,
  download: undefined,
  partSize: undefined,
  wholeMaxSize: undefined,
  concurrency: undefined,
  autoDedup: true,
  draggable: false,
  readonly: false,
  required: false,
  errorMessage: '',
  emptyText: FILE_EMPTY_TEXT,
  showProgress: true,
  downloadable: true,
  previewable: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: UploadFieldItem[]]
  change: [value: UploadFieldItem[]]
  remove: [id: string]
  retry: [id: string]
  cancel: [id: string]
  fail: [payload: { id: string; code?: number; message: string }]
  'limit-exceed': [limit: number]
  invalid: [message: string]
  progress: [payload: { id: string; percent: number }]
  done: [ref: FileRef]
}>()

const state = useBaseFileUpload({
  ready: props.ready,
  kind: 'file',
  multiple: props.multiple,
  ...(props.limit === undefined ? {} : { limit: props.limit }),
  accept: props.accept,
  ...(props.maxSize === undefined ? {} : { maxSize: props.maxSize * 1024 * 1024 }),
  ...(props.partSize === undefined ? {} : { partSize: props.partSize }),
  ...(props.wholeMaxSize === undefined ? {} : { wholeMaxSize: props.wholeMaxSize }),
  ...(props.concurrency === undefined ? {} : { concurrency: props.concurrency }),
  autoDedup: props.autoDedup,
  draggable: props.draggable,
  readonlyView: props.readonly,
  ...(props.transport === undefined ? {} : { transport: props.transport }),
  ...(props.presigned === undefined ? {} : { presigned: props.presigned }),
})

if (props.download !== undefined) {
  state.upload.setDownload(props.download)
}

const inputRef = vueRef<HTMLInputElement | undefined>(undefined)
const previewVisible = vueRef(false)
const previewIndex = vueRef(0)
const dragOver = vueRef(false)

/** 生效禁用（件级 ∨ 占位）。 */
const effectiveDisabled = computed(() => props.disabled || state.disabled.value)
/** 引用列表。 */
const refs = computed<FileRef[]>(() => state.refs.value)
/** 是否降级。 */
const degraded = computed(() => state.degraded.value)

/**
 * 取文件项展示文案（失效标记）。
 *
 * @param ref 引用。
 * @returns 展示文案。
 */
function labelOf(ref: FileRef): string {
  return fileRefLabel(ref)
}

/**
 * 取文件体积文案。
 *
 * @param ref 引用。
 * @returns 体积文案（缺失空串）。
 */
function sizeText(ref: FileRef): string {
  return ref.size === undefined ? '' : formatFileSize(ref.size)
}

/**
 * 取任务进度（在途 / 失败态）。
 *
 * @param ref 引用。
 * @returns 任务快照；无在途任务 `undefined`。
 */
function taskOf(ref: FileRef) {
  return state.taskOfFile(ref.id)
}

/**
 * 取任务进度百分比。
 *
 * @param ref 引用。
 * @returns 进度（0 ~ 100）。
 */
function percentOf(ref: FileRef): number {
  return state.taskOfFile(ref.id)?.percent ?? 0
}

/**
 * 取任务阶段。
 *
 * @param ref 引用。
 * @returns 阶段；无在途任务 `undefined`。
 */
function phaseOf(ref: FileRef): string | undefined {
  return state.taskOfFile(ref.id)?.phase
}

/**
 * 是否在途任务（待传 / 哈希 / 上传）。
 *
 * @param ref 引用。
 * @returns 是否在途。
 */
function isBusy(ref: FileRef): boolean {
  const phase = phaseOf(ref)
  return phase === 'pending' || phase === 'hashing' || phase === 'uploading' || phase === 'merging'
}

/**
 * 取预览文件列表。
 *
 * @returns 预览文件列表。
 */
function previewFiles(): PreviewFile[] {
  return refs.value.map((ref) => ({
    id: ref.id,
    name: ref.name,
    ...(ref.mime === undefined ? {} : { mimeType: ref.mime }),
    ...(ref.size === undefined ? {} : { size: ref.size }),
    ...(ref.url === undefined ? {} : { url: ref.url }),
  }))
}

/**
 * 预签名取址（供预览件）。
 *
 * @param file 预览文件。
 */
async function previewFetcher(file: PreviewFile): Promise<{ url: string; expiresAt: number }> {
  const url = await state.previewUrlOf(file.id)
  return { url: url ?? '', expiresAt: 0 }
}

/**
 * 打开文件选择。
 */
function openPicker(): void {
  if (effectiveDisabled.value || props.readonly) {
    return
  }
  inputRef.value?.click()
}

/**
 * 选择文件（校验 + 入队）。
 *
 * @param files 文件列表。
 */
function acceptFiles(files: File[]): void {
  if (files.length === 0) {
    return
  }
  const result = state.acceptFiles(files.map((file) => ({ file, meta: metaOf(file) })))
  if (result.rejected.length > 0) {
    emit('invalid', result.rejected[0]?.message ?? '')
  }
  if (state.limitExceeded.value) {
    emit('limit-exceed', props.limit ?? 0)
  }
}

/**
 * 读取文件元信息。
 *
 * @param file 文件对象。
 */
function metaOf(file: File): { name: string; size: number; mime: string; lastModified: number } {
  return { name: file.name, size: file.size, mime: file.type, lastModified: file.lastModified }
}

/**
 * 文件选择回调。
 *
 * @param event 变更事件。
 */
function onPick(event: Event): void {
  const input = event.target as HTMLInputElement
  acceptFiles(Array.from(input.files ?? []))
  input.value = ''
}

/**
 * 拖放回调。
 *
 * @param event 拖放事件。
 */
function onDrop(event: DragEvent): void {
  dragOver.value = false
  if (effectiveDisabled.value || props.readonly) {
    return
  }
  acceptFiles(Array.from(event.dataTransfer?.files ?? []))
}

/**
 * 移除文件。
 *
 * @param id 文件标识。
 */
function onRemove(id: string): void {
  emit('remove', id)
  state.remove(id)
}

/**
 * 重试失败任务。
 *
 * @param ref 引用。
 */
function onRetry(ref: FileRef): void {
  const taskId = state.upload.taskIdOfFile(ref.id)
  if (taskId !== undefined) {
    emit('retry', ref.id)
    void state.retryTask(taskId)
  }
}

/**
 * 取消在途任务。
 *
 * @param ref 引用。
 */
function onCancel(ref: FileRef): void {
  const taskId = state.upload.taskIdOfFile(ref.id)
  if (taskId !== undefined) {
    emit('cancel', ref.id)
    state.cancelTask(taskId)
  }
}

/**
 * 下载文件。
 *
 * @param ref 引用。
 */
function onDownload(ref: FileRef): void {
  void state.downloadFile(ref.id)
}

/**
 * 预览文件。
 *
 * @param ref 引用。
 */
function onPreview(ref: FileRef): void {
  previewIndex.value = refs.value.findIndex((entry) => entry.id === ref.id)
  previewVisible.value = true
}

watch(
  () => props.ready,
  (value) => state.setReady(value),
)
watch(
  () => props.transport,
  (value) => state.setTransport(value),
)
watch(
  () => props.modelValue,
  (items) => {
    const ids = items.map((item) => item.id)
    if (!sameIds(ids, state.selectedIds.value)) {
      state.syncValue(ids)
      state.upload.mergeRefs(items.map((item) => ({ id: item.id, name: item.name, ...(item.url === undefined ? {} : { url: item.url }) })))
    }
  },
  { immediate: true },
)
watch(
  () => props.errorMessage,
  (value) => {
    if (value !== '') {
      emit('invalid', value)
    }
  },
)
watch(
  () => state.value.value,
  () => {
    const next = refs.value.map((ref) => ({ id: ref.id, name: ref.name, ...(ref.url === undefined ? {} : { url: ref.url }) }))
    if (!sameIds(next.map((item) => item.id), props.modelValue.map((item) => item.id))) {
      emit('update:modelValue', next)
      emit('change', next)
    }
  },
)
watch(
  () => state.tasks.value,
  (tasks) => {
    for (const task of tasks) {
      const ref = refs.value.find((entry) => state.upload.taskIdOfFile(entry.id) === task.id)
      const id = ref?.id ?? task.fileId ?? task.id
      emit('progress', { id, percent: task.percent })
      if (task.phase === 'failed') {
        emit('fail', { id, ...(task.errorCode === undefined ? {} : { code: task.errorCode }), message: task.errorMessage })
      }
      if (task.phase === 'done') {
        const done = refs.value.find((entry) => entry.id === task.fileId)
        if (done !== undefined) {
          emit('done', done)
        }
      }
    }
  },
)

/**
 * 比较标识列表（顺序与内容一致）。
 *
 * @param left 左列表。
 * @param right 右列表。
 * @returns 是否一致。
 */
function sameIds(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index])
}

/**
 * 是否图片引用。
 *
 * @param ref 引用。
 * @returns 是否图片。
 */
function isImage(ref: FileRef): boolean {
  return isImageFile(ref.name, ref.mime ?? '')
}

/**
 * 是否失效引用。
 *
 * @param ref 引用。
 * @returns 是否失效。
 */
function isInvalid(ref: FileRef): boolean {
  return isFileRefInvalid(ref)
}
</script>

<template>
  <div
    class="bms-file-upload-field"
    :data-ready="state.ready.value"
    :data-degraded="degraded"
    :data-disabled="effectiveDisabled"
  >
    <slot v-if="degraded" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <slot v-if="!readonly" name="live" :disabled="effectiveDisabled" :open="openPicker">
        <div
          class="bms-file-upload-field__dropzone"
          :class="{ 'is-dragover': dragOver }"
          data-test="file-dropzone"
          @click="openPicker"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="onDrop"
        >
          <span class="bms-file-upload-field__tip">{{ placeholder }}</span>
          <input
            ref="inputRef"
            class="bms-file-upload-field__input"
            data-test="file-input"
            type="file"
            :accept="accept"
            :multiple="multiple"
            :disabled="effectiveDisabled"
            @change="onPick"
          />
        </div>
      </slot>

      <ul v-if="refs.length > 0" class="bms-file-upload-field__list">
        <li
          v-for="ref in refs"
          :key="ref.id"
          class="bms-file-upload-field__item"
          :class="{ 'is-invalid': isInvalid(ref) }"
          :data-test="`file-${ref.id}`"
        >
          <span class="bms-file-upload-field__name" :title="labelOf(ref)">{{ labelOf(ref) }}</span>
          <span v-if="sizeText(ref) !== ''" class="bms-file-upload-field__size">{{ sizeText(ref) }}</span>
          <span
            v-if="showProgress && isBusy(ref)"
            class="bms-file-upload-field__progress"
            :data-test="`file-progress-${ref.id}`"
          >
            <i :style="{ width: `${percentOf(ref)}%` }" />
          </span>
          <span class="bms-file-upload-field__actions">
            <button
              v-if="!readonly"
              type="button"
              :disabled="effectiveDisabled"
              @click="onRemove(ref.id)"
            >
              移除
            </button>
            <button
              v-if="previewable && isImage(ref)"
              type="button"
              :disabled="effectiveDisabled || isInvalid(ref)"
              @click="onPreview(ref)"
            >
              预览
            </button>
            <button
              v-if="downloadable && !isInvalid(ref)"
              type="button"
              :disabled="effectiveDisabled"
              @click="onDownload(ref)"
            >
              下载
            </button>
            <button
              v-if="phaseOf(ref) === 'failed'"
              type="button"
              data-test="file-retry"
              :disabled="effectiveDisabled"
              @click="onRetry(ref)"
            >
              重试
            </button>
            <button
              v-if="isBusy(ref)"
              type="button"
              data-test="file-cancel"
              @click="onCancel(ref)"
            >
              取消
            </button>
          </span>
          <slot name="item" :file="ref" :task="taskOf(ref)" />
        </li>
      </ul>
      <div v-else class="bms-file-upload-field__empty" data-test="file-empty">{{ emptyText }}</div>

      <FilePreview
        v-if="previewVisible"
        :ready="true"
        :files="previewFiles()"
        :index="previewIndex"
        :visible="previewVisible"
        :presigned-fetcher="previewFetcher"
        @update:visible="previewVisible = $event"
        @update:index="previewIndex = $event"
        @close="previewVisible = false"
      />
    </template>
  </div>
</template>

<style scoped>
.bms-file-upload-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bms-file-upload-field__dropzone {
  position: relative;
  padding: 16px;
  border: 1px dashed var(--bms-file-drop-border);
  border-radius: 6px;
  background: var(--bms-file-drop-bg);
  color: var(--bms-file-icon-color);
  text-align: center;
  cursor: pointer;
}
.bms-file-upload-field__dropzone.is-dragover {
  border-color: var(--bms-file-drop-active-border);
}
.bms-file-upload-field__input {
  display: none;
}
.bms-file-upload-field__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.bms-file-upload-field__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--bms-file-border);
  border-radius: 4px;
  background: var(--bms-file-item-bg);
}
.bms-file-upload-field__item.is-invalid {
  color: var(--bms-file-marker-invalid-color);
}
.bms-file-upload-field__size {
  color: var(--bms-file-icon-color);
}
.bms-file-upload-field__progress {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--bms-file-progress-bg);
  overflow: hidden;
}
.bms-file-upload-field__progress i {
  display: block;
  height: 100%;
  background: var(--bms-file-progress-bar);
}
.bms-file-upload-field__actions {
  display: flex;
  gap: 4px;
  margin-left: auto;
}
.bms-file-upload-field__empty {
  color: var(--bms-file-icon-color);
}
</style>
