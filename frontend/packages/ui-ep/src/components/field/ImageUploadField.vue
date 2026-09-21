<script setup lang="ts">
// 图片上传字段（06_07）：缩略图网格、多图排序、尺寸与比例校验、压缩、裁剪（头像圆形 / 通用比例）、只读回显。
import {
  FILE_EMPTY_TEXT,
  FILE_PLACEHOLDER_TEXT,
  IMAGE_COMPRESS_MAX_EDGE,
  IMAGE_COMPRESS_MIN_SIZE,
  IMAGE_COMPRESS_QUALITY,
  IMAGE_COMPRESS_SKIP_SIZE,
  fileRefLabel,
  isFileRefInvalid,
  isLocalFileRef,
  type BaseFileDownload,
  type BasePresignedUrl,
  type FileMeta,
  type FileRef,
  type ImageCheckOptions,
  type ImageCropShape,
  type UploadTransportAdapter,
} from '@bms/core'
import { computed, onScopeDispose, ref as vueRef, watch } from 'vue'

import { useBaseFileUpload } from '../../composables/useBaseFileUpload'
import { compressImage, createObjectUrl, planImageCompress, readImageDimension, revokeObjectUrl } from '../../utils/imageProcess'
import FilePreview, { type PreviewFile } from '../display/FilePreview.vue'
import ImageCropDialog from './ImageCropDialog.vue'

interface Props {
  /** 图片标识（单值 / 数组）。 */
  modelValue?: string | string[]
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 是否多选（缺省多选）。 */
  multiple?: boolean
  /** 数量上限（缺省 9）。 */
  limit?: number
  /** 接受类型。 */
  accept?: string
  /** 单图大小上限（字节）。 */
  maxSize?: number
  /** 图片压缩。 */
  compress?: boolean
  /** 压缩最大边长（像素）。 */
  compressMaxEdge?: number
  /** 压缩质量。 */
  compressQuality?: number
  /** 图片裁剪。 */
  crop?: boolean
  /** 裁剪形态。 */
  cropShape?: ImageCropShape
  /** 裁剪比例。 */
  cropAspect?: number
  /** 尺寸与比例校验。 */
  imageOptions?: ImageCheckOptions
  /** 多图排序（缺省开启）。 */
  draggable?: boolean
  /** 上传通路（未注入即占位零请求）。 */
  transport?: UploadTransportAdapter
  /** 预签名能力。 */
  presigned?: BasePresignedUrl
  /** 下载触发能力。 */
  download?: BaseFileDownload
  /** 禁用。 */
  disabled?: boolean
  /** 只读回显。 */
  readonly?: boolean
  /** 占位文案。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 空态文案。 */
  emptyText?: string
  /** 错误文案。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: false,
  multiple: true,
  limit: 9,
  accept: 'image/png,image/jpeg,image/webp',
  maxSize: undefined,
  compress: true,
  compressMaxEdge: IMAGE_COMPRESS_MAX_EDGE,
  compressQuality: IMAGE_COMPRESS_QUALITY,
  crop: false,
  cropShape: 'rect',
  cropAspect: 1,
  imageOptions: undefined,
  draggable: true,
  transport: undefined,
  presigned: undefined,
  download: undefined,
  disabled: false,
  readonly: false,
  placeholder: '点击或拖拽上传图片',
  degradeText: FILE_PLACEHOLDER_TEXT,
  emptyText: FILE_EMPTY_TEXT,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string | string[] | undefined]
  change: [value: string | string[] | undefined]
  remove: [id: string]
  retry: [id: string]
  cancel: [id: string]
  fail: [payload: { id: string; code?: number; message: string }]
  'limit-exceed': [limit: number]
  invalid: [message: string]
  crop: [payload: { name: string }]
  progress: [payload: { id: string; percent: number }]
  done: [ref: FileRef]
}>()

const state = useBaseFileUpload({
  ready: props.ready,
  kind: 'image',
  multiple: props.multiple,
  limit: props.limit,
  accept: props.accept,
  ...(props.maxSize === undefined ? {} : { maxSize: props.maxSize }),
  compress: props.compress,
  crop: props.crop,
  cropShape: props.cropShape,
  cropAspect: props.cropAspect,
  ...(props.imageOptions === undefined ? {} : { imageOptions: props.imageOptions }),
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
const dragIndex = vueRef(-1)
const cropVisible = vueRef(false)
const cropSource = vueRef<unknown>(undefined)
const pendingCrop = vueRef<{ file: File } | undefined>(undefined)
/** 本地对象 URL（键 `名称:体积`，跨服务端标识替换稳定）。 */
const localUrls = new Map<string, string>()
const resolvedUrls = vueRef<Record<string, string>>({})

/** 生效禁用。 */
const effectiveDisabled = computed(() => props.disabled || state.disabled.value)
/** 引用列表。 */
const refs = computed<FileRef[]>(() => state.refs.value)
/** 是否头像形态（单图 + 圆形）。 */
const avatar = computed(() => !props.multiple && props.cropShape === 'circle')

/**
 * 取缩略图地址。
 *
 * @param ref 引用。
 * @returns 地址或 `undefined`。
 */
function thumbUrl(ref: FileRef): string | undefined {
  return ref.url ?? resolvedUrls.value[ref.id] ?? localUrls.get(keyOf(ref))
}

/**
 * 取本地 URL 键。
 *
 * @param ref 引用。
 * @returns 键。
 */
function keyOf(ref: FileRef): string {
  return `${ref.name}:${ref.size ?? 0}`
}

/**
 * 展示文案（失效标记）。
 *
 * @param ref 引用。
 * @returns 展示文案。
 */
function labelOf(ref: FileRef): string {
  return fileRefLabel(ref)
}

/**
 * 是否失效。
 *
 * @param ref 引用。
 * @returns 是否失效。
 */
function isInvalid(ref: FileRef): boolean {
  return isFileRefInvalid(ref)
}

/**
 * 任务阶段。
 *
 * @param ref 引用。
 * @returns 阶段或 `undefined`。
 */
function phaseOf(ref: FileRef): string | undefined {
  return state.taskOfFile(ref.id)?.phase
}

/**
 * 任务进度。
 *
 * @param ref 引用。
 * @returns 进度（0 ~ 100）。
 */
function percentOf(ref: FileRef): number {
  return state.taskOfFile(ref.id)?.percent ?? 0
}

/**
 * 打开选择。
 */
function openPicker(): void {
  if (effectiveDisabled.value || props.readonly) {
    return
  }
  inputRef.value?.click()
}

/**
 * 文件选择回调。
 *
 * @param event 变更事件。
 */
function onPick(event: Event): void {
  const input = event.target as HTMLInputElement
  void acceptFiles(Array.from(input.files ?? []))
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
  void acceptFiles(Array.from(event.dataTransfer?.files ?? []))
}

/**
 * 接受图片（尺寸探测 → 压缩 → 裁剪 → 入队）。
 *
 * @param files 文件列表。
 */
async function acceptFiles(files: File[]): Promise<void> {
  if (files.length === 0) {
    return
  }
  if (props.crop && files.length > 0) {
    pendingCrop.value = { file: files[0] as File }
    cropSource.value = files[0]
    cropVisible.value = true
    emit('crop', { name: (files[0] as File).name })
    return
  }
  const prepared: { file: unknown; meta: FileMeta }[] = []
  for (const file of files) {
    prepared.push(await prepareFile(file))
  }
  submit(prepared)
}

/**
 * 裁剪确认（以产物入队）。
 *
 * @param payload 裁剪产物。
 */
async function onCropped(payload: { blob: Blob }): Promise<void> {
  const pending = pendingCrop.value
  pendingCrop.value = undefined
  cropSource.value = undefined
  if (pending === undefined) {
    return
  }
  const cropped = toFile(payload.blob, pending.file.name)
  submit([await prepareFile(cropped)])
}

/**
 * 提交入队（并登记本地缩略图地址）。
 *
 * @param prepared 预处理结果。
 */
function submit(prepared: { file: unknown; meta: FileMeta }[]): void {
  const result = state.acceptFiles(prepared)
  for (const ref of result.added) {
    const entry = prepared.find((item) => item.meta.name === ref.name && item.meta.size === ref.size)
    const url = entry === undefined ? undefined : createObjectUrl(entry.file)
    if (url !== undefined) {
      localUrls.set(keyOf(ref), url)
    }
  }
  if (result.rejected.length > 0) {
    emit('invalid', result.rejected[0]?.message ?? '')
  }
  if (state.limitExceeded.value) {
    emit('limit-exceed', props.limit)
  }
}

/**
 * 预处理单图（尺寸探测 / 压缩）。
 *
 * @param file 文件。
 * @returns 预处理结果。
 */
async function prepareFile(file: File): Promise<{ file: unknown; meta: FileMeta }> {
  const dimension = await readImageDimension(file)
  let current: Blob = file
  if (props.compress && file.size <= IMAGE_COMPRESS_SKIP_SIZE) {
    const decision = planImageCompress(
      {
        name: file.name,
        size: file.size,
        mime: file.type,
        ...(dimension === undefined ? {} : { dimension }),
      },
      { maxEdge: props.compressMaxEdge, minSize: IMAGE_COMPRESS_MIN_SIZE },
    )
    if (decision.compress) {
      const compressed = await compressImage(file, { maxEdge: props.compressMaxEdge, quality: props.compressQuality })
      if (compressed instanceof Blob) {
        current = compressed
      }
    }
  }
  return {
    file: current === file ? file : toFile(current, file.name),
    meta: {
      name: file.name,
      size: current.size,
      mime: current.type === '' ? file.type : current.type,
      lastModified: file.lastModified,
      ...(dimension === undefined ? {} : { dimension }),
    },
  }
}

/**
 * 构造文件对象（`File` 能力缺失回退原 Blob）。
 *
 * @param blob 内容。
 * @param name 文件名。
 * @returns 文件对象。
 */
function toFile(blob: Blob, name: string): File {
  if (typeof File === 'function') {
    return new File([blob], name, { type: blob.type, lastModified: Date.now() })
  }
  return blob as unknown as File
}

/**
 * 移除图片。
 *
 * @param ref 引用。
 */
function onRemove(ref: FileRef): void {
  emit('remove', ref.id)
  const url = localUrls.get(keyOf(ref))
  revokeObjectUrl(url)
  localUrls.delete(keyOf(ref))
  state.remove(ref.id)
}

/**
 * 重试。
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
 * 取消。
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
 * 预览。
 *
 * @param ref 引用。
 */
function onPreview(ref: FileRef): void {
  previewIndex.value = refs.value.findIndex((entry) => entry.id === ref.id)
  previewVisible.value = true
}

/**
 * 拖拽开始。
 *
 * @param index 索引。
 */
function onDragStart(index: number): void {
  dragIndex.value = index
}

/**
 * 拖拽落点（排序）。
 *
 * @param index 目标索引。
 */
function onDragOverItem(index: number): void {
  const from = dragIndex.value
  dragIndex.value = -1
  if (from >= 0 && from !== index) {
    state.moveFile(from, index)
  }
}

/**
 * 预览文件列表。
 *
 * @returns 预览文件列表。
 */
function previewFiles(): PreviewFile[] {
  return refs.value.map((ref) => ({
    id: ref.id,
    name: ref.name,
    mimeType: ref.mime ?? 'image/*',
    ...(ref.size === undefined ? {} : { size: ref.size }),
    ...(thumbUrl(ref) === undefined ? {} : { url: thumbUrl(ref) }),
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
  (value) => {
    const ids = value === undefined ? [] : Array.isArray(value) ? value : [value]
    if (!sameIds(ids.map(String), state.selectedIds.value)) {
      state.syncValue(value)
    }
  },
  { immediate: true },
)
watch(
  () => state.value.value,
  (value) => {
    const ids = value === undefined ? [] : Array.isArray(value) ? value : [value]
    if (!sameIds(ids.map(String), (props.modelValue === undefined ? [] : Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]).map(String))) {
      emit('update:modelValue', value)
      emit('change', value)
    }
  },
)
watch(
  refs,
  (next) => {
    const keys = new Set(next.map((ref) => keyOf(ref)))
    for (const [key, url] of [...localUrls]) {
      if (!keys.has(key)) {
        revokeObjectUrl(url)
        localUrls.delete(key)
      }
    }
    for (const ref of next) {
      if (isLocalFileRef(ref) || ref.url !== undefined || resolvedUrls.value[ref.id] !== undefined) {
        continue
      }
      void state.previewUrlOf(ref.id).then((url) => {
        if (url !== undefined && url !== '') {
          resolvedUrls.value = { ...resolvedUrls.value, [ref.id]: url }
        }
      })
    }
  },
  { immediate: true },
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
watch(
  () => props.errorMessage,
  (value) => {
    if (value !== '') {
      emit('invalid', value)
    }
  },
)

onScopeDispose(() => {
  for (const url of localUrls.values()) {
    revokeObjectUrl(url)
  }
  localUrls.clear()
})

/**
 * 比较标识列表。
 *
 * @param left 左列表。
 * @param right 右列表。
 * @returns 是否一致。
 */
function sameIds(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index])
}
</script>

<template>
  <div
    class="bms-image-upload-field"
    :data-ready="state.ready.value"
    :data-degraded="state.degraded.value"
    :data-avatar="avatar"
  >
    <slot v-if="state.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <div class="bms-image-upload-field__grid" :data-test="readonly ? 'image-readonly' : 'image-upload-field'">
        <div
          v-for="(ref, index) in refs"
          :key="ref.id"
          class="bms-image-upload-field__thumb"
          :class="{ 'is-invalid': isInvalid(ref), 'is-circle': avatar }"
          :data-test="`image-thumb-${ref.id}`"
          :draggable="draggable && !readonly && !avatar"
          @dragstart="onDragStart(index)"
          @dragover.prevent
          @drop.prevent="onDragOverItem(index)"
        >
          <img v-if="thumbUrl(ref) !== undefined" :src="thumbUrl(ref)" :alt="labelOf(ref)" @click="onPreview(ref)" />
          <span v-else class="bms-image-upload-field__placeholder">{{ labelOf(ref) }}</span>
          <span
            v-if="phaseOf(ref) !== undefined && phaseOf(ref) !== 'done' && phaseOf(ref) !== 'failed'"
            class="bms-image-upload-field__progress"
            :data-test="`image-progress-${ref.id}`"
          >
            <i :style="{ width: `${percentOf(ref)}%` }" />
          </span>
          <span class="bms-image-upload-field__actions">
            <button
              v-if="!readonly"
              type="button"
              :data-test="`image-remove-${ref.id}`"
              :disabled="effectiveDisabled"
              @click="onRemove(ref)"
            >
              移除
            </button>
            <button
              v-if="phaseOf(ref) === 'failed'"
              type="button"
              data-test="image-retry"
              :disabled="effectiveDisabled"
              @click="onRetry(ref)"
            >
              重试
            </button>
            <button
              v-if="phaseOf(ref) === 'uploading' || phaseOf(ref) === 'hashing' || phaseOf(ref) === 'pending'"
              type="button"
              data-test="image-cancel"
              @click="onCancel(ref)"
            >
              取消
            </button>
          </span>
          <slot name="item" :file="ref" />
        </div>

        <div
          v-if="!readonly && state.upload.canAddMore"
          class="bms-image-upload-field__add"
          :class="{ 'is-dragover': dragOver }"
          data-test="image-add"
          @click="openPicker"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="onDrop"
        >
          <span>{{ placeholder }}</span>
          <input
            ref="inputRef"
            class="bms-image-upload-field__input"
            type="file"
            :accept="accept"
            :multiple="multiple"
            :disabled="effectiveDisabled"
            @change="onPick"
          />
        </div>
      </div>

      <div v-if="refs.length === 0" class="bms-image-upload-field__empty" data-test="image-empty">{{ emptyText }}</div>

      <ImageCropDialog
        v-if="crop"
        :visible="cropVisible"
        :source="cropSource"
        :shape="cropShape"
        :aspect="cropAspect"
        @update:visible="cropVisible = $event"
        @confirm="onCropped"
        @cancel="pendingCrop = undefined"
        @fail="emit('invalid', $event)"
      />

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
.bms-image-upload-field__grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.bms-image-upload-field__thumb {
  position: relative;
  width: 96px;
  height: 96px;
  border: 1px solid var(--bms-file-border);
  border-radius: 4px;
  background: var(--bms-file-item-bg);
  overflow: hidden;
}
.bms-image-upload-field__thumb.is-circle {
  width: 72px;
  height: 72px;
  border-radius: 50%;
}
.bms-image-upload-field__thumb.is-invalid {
  color: var(--bms-file-marker-invalid-color);
}
.bms-image-upload-field__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  cursor: pointer;
}
.bms-image-upload-field__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 4px;
  color: var(--bms-file-icon-color);
  font-size: 12px;
  text-align: center;
  word-break: break-all;
}
.bms-image-upload-field__progress {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 4px;
  background: var(--bms-file-progress-bg);
}
.bms-image-upload-field__progress i {
  display: block;
  height: 100%;
  background: var(--bms-file-progress-bar);
}
.bms-image-upload-field__actions {
  position: absolute;
  top: 2px;
  right: 2px;
  display: flex;
  gap: 2px;
}
.bms-image-upload-field__add {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  border: 1px dashed var(--bms-file-drop-border);
  border-radius: 4px;
  background: var(--bms-file-drop-bg);
  color: var(--bms-file-icon-color);
  font-size: 12px;
  text-align: center;
  cursor: pointer;
}
.bms-image-upload-field__add.is-dragover {
  border-color: var(--bms-file-drop-active-border);
}
.bms-image-upload-field__input {
  display: none;
}
.bms-image-upload-field__empty {
  margin-top: 4px;
  color: var(--bms-file-icon-color);
}
</style>
