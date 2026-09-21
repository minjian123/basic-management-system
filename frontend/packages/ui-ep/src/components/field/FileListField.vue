<script setup lang="ts">
// 只读文件列表件（06_07）：文件名 / 大小 / 图标、下载、预览（图片 / PDF）、失效占位。
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

interface Props {
  /** 文件标识（单值 / 数组）。 */
  modelValue?: string | string[]
  /** 数据通路是否就绪（缺省 true）。 */
  ready?: boolean
  /** 上传通路（未注入即占位零请求）。 */
  transport?: UploadTransportAdapter
  /** 预签名能力。 */
  presigned?: BasePresignedUrl
  /** 下载触发能力。 */
  download?: BaseFileDownload
  /** 可下载。 */
  downloadable?: boolean
  /** 可预览。 */
  previewable?: boolean
  /** 空态文案。 */
  emptyText?: string
  /** 降级文案。 */
  degradeText?: string
  /** 错误文案。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: true,
  transport: undefined,
  presigned: undefined,
  download: undefined,
  downloadable: true,
  previewable: true,
  emptyText: FILE_EMPTY_TEXT,
  degradeText: FILE_PLACEHOLDER_TEXT,
  errorMessage: '',
})

const emit = defineEmits<{
  retry: []
  download: [ref: FileRef]
  preview: [ref: FileRef]
  invalid: [message: string]
}>()

const state = useBaseFileUpload({
  ready: props.ready,
  kind: 'file',
  multiple: true,
  readonlyView: true,
  ...(props.transport === undefined ? {} : { transport: props.transport }),
  ...(props.presigned === undefined ? {} : { presigned: props.presigned }),
})

if (props.download !== undefined) {
  state.upload.setDownload(props.download)
}

const previewVisible = vueRef(false)
const previewIndex = vueRef(0)
const refs = computed<FileRef[]>(() => state.refs.value)

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
 * 体积文案。
 *
 * @param ref 引用。
 * @returns 体积文案（缺失空串）。
 */
function sizeText(ref: FileRef): string {
  return ref.size === undefined ? '' : formatFileSize(ref.size)
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

/**
 * 预览文件列表。
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
 * 下载。
 *
 * @param ref 引用。
 */
function onDownload(ref: FileRef): void {
  emit('download', ref)
  void state.downloadFile(ref.id)
}

/**
 * 预览。
 *
 * @param ref 引用。
 */
function onPreview(ref: FileRef): void {
  previewIndex.value = refs.value.findIndex((entry) => entry.id === ref.id)
  previewVisible.value = true
  emit('preview', ref)
}

watch(
  () => props.ready,
  (value) => state.setReady(value),
)
watch(
  () => props.modelValue,
  (value) => {
    state.syncValue(value)
  },
  { immediate: true },
)
watch(
  () => props.transport,
  (value) => state.setTransport(value),
)
</script>

<template>
  <div class="bms-file-list-field" :data-ready="state.ready.value" :data-degraded="state.degraded.value">
    <slot v-if="state.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <ul v-if="refs.length > 0" class="bms-file-list-field__list" data-test="file-list-field">
        <li
          v-for="ref in refs"
          :key="ref.id"
          class="bms-file-list-field__item"
          :class="{ 'is-invalid': isInvalid(ref) }"
          :data-test="`file-list-item-${ref.id}`"
        >
          <img
            v-if="isImage(ref) && ref.url !== undefined"
            class="bms-file-list-field__thumb"
            :src="ref.url"
            :alt="ref.name"
          />
          <span class="bms-file-list-field__name">{{ labelOf(ref) }}</span>
          <span v-if="sizeText(ref) !== ''" class="bms-file-list-field__size" :data-test="`file-size-${ref.id}`">
            {{ sizeText(ref) }}
          </span>
          <span v-if="isInvalid(ref)" class="bms-file-list-field__mark" :data-test="`file-mark-invalid-${ref.id}`">
            文件已失效
          </span>
          <span class="bms-file-list-field__actions">
            <button
              v-if="previewable && !isInvalid(ref)"
              type="button"
              :data-test="`file-preview-${ref.id}`"
              @click="onPreview(ref)"
            >
              预览
            </button>
            <button
              v-if="downloadable && !isInvalid(ref)"
              type="button"
              :data-test="`file-download-${ref.id}`"
              @click="onDownload(ref)"
            >
              下载
            </button>
          </span>
          <slot name="item" :file="ref" />
          <slot name="actions" :file="ref" />
        </li>
      </ul>
      <div v-else class="bms-file-list-field__empty" data-test="file-empty">{{ emptyText }}</div>

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
.bms-file-list-field__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.bms-file-list-field__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--bms-file-border);
  border-radius: 4px;
  background: var(--bms-file-item-bg);
}
.bms-file-list-field__item.is-invalid {
  color: var(--bms-file-marker-invalid-color);
}
.bms-file-list-field__thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 4px;
}
.bms-file-list-field__size {
  color: var(--bms-file-icon-color);
}
.bms-file-list-field__mark {
  color: var(--bms-file-marker-invalid-color);
}
.bms-file-list-field__actions {
  display: flex;
  gap: 4px;
  margin-left: auto;
}
.bms-file-list-field__empty {
  color: var(--bms-file-icon-color);
}
</style>
