<script setup lang="ts">
// 文件预览（07_03）：类型分发（图片 / PDF / 音视频 / 文本 / 其他降级下载）、预签名获取与失效重取、下载。
import { ElButton } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useBasePresignedUrl } from '../../composables/useBasePresignedUrl'
import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'
import { triggerDownload } from '../../utils/downloadFile'
import { onGlobalKeydown } from '../../utils/keyboard'
import type { PresignedResult } from '@bms/core'

/** 待预览文件。 */
export interface PreviewFile {
  /** 文件 ID。 */
  id: string
  /** 文件名。 */
  name: string
  /** MIME 类型。 */
  mimeType?: string
  /** 字节大小。 */
  size?: number
  /** 直接可用的地址（预签名或静态）。 */
  url?: string
}

/** 预览失败原因。 */
export type PreviewErrorReason = 'expired' | 'unsupported' | 'load-failed' | 'forbidden'

/** 预览类型。 */
export type PreviewKind = 'image' | 'video' | 'audio' | 'pdf' | 'text' | 'other'

/** 预览形态。 */
export type PreviewMode = 'overlay' | 'drawer' | 'inline'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 文件列表。 */
  files?: PreviewFile[]
  /** 当前索引。 */
  index?: number
  /** 是否显示。 */
  visible?: boolean
  /** 预签名获取器（宿主注入；未注入时降级用 `file.url`）。 */
  presignedFetcher?: (file: PreviewFile) => Promise<PresignedResult>
  /** 文本预览截断上限（字节）。 */
  textLimit?: number
  /** 预览形态（遮罩层 / 抽屉 / 页内嵌）。 */
  mode?: PreviewMode
  /** 是否显示图片缩略图条。 */
  thumbs?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  files: () => [],
  index: 0,
  visible: true,
  presignedFetcher: undefined,
  textLimit: 51200,
  mode: 'overlay',
  thumbs: true,
  degradeText: '文件预览未就绪（占位）',
})

const emit = defineEmits<{
  'update:index': [index: number]
  'update:visible': [visible: boolean]
  change: [file: PreviewFile, index: number]
  close: []
  error: [payload: { file: PreviewFile; reason: PreviewErrorReason }]
  download: [file: PreviewFile]
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })
const presigned = useBasePresignedUrl()

const sourceUrl = ref('')
const textContent = ref('')
const errorReason = ref<PreviewErrorReason | ''>('')
const retried = ref(false)
const zoom = ref(1)
const rotation = ref(0)

const current = computed<PreviewFile | undefined>(() => props.files[props.index])

const kind = computed<PreviewKind>(() => {
  const mime = current.value?.mimeType ?? ''
  if (mime.startsWith('image/')) {
    return 'image'
  }
  if (mime.startsWith('video/')) {
    return 'video'
  }
  if (mime.startsWith('audio/')) {
    return 'audio'
  }
  if (mime === 'application/pdf') {
    return 'pdf'
  }
  if (mime.startsWith('text/') || /\.(txt|csv|json|log|md)$/i.test(current.value?.name ?? '')) {
    return 'text'
  }
  return 'other'
})

const errorText = computed(() => {
  switch (errorReason.value) {
    case 'unsupported':
      return '该类型不支持在线预览，请下载查看'
    case 'expired':
      return '文件地址已失效，请刷新后重试'
    case 'forbidden':
      return '无权限访问该文件'
    case 'load-failed':
      return '文件加载失败'
    default:
      return ''
  }
})

const imageStyle = computed<Record<string, string>>(() => ({
  transform: `scale(${zoom.value}) rotate(${rotation.value}deg)`,
}))

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

watch(
  () => props.presignedFetcher,
  (fetcher) => {
    presigned.setFetcher(fetcher ? () => fetcher(props.files[props.index] as PreviewFile) : undefined)
  },
)

async function loadText(url: string): Promise<void> {
  try {
    const response = await fetch(url)
    const text = await response.text()
    textContent.value = text.slice(0, props.textLimit)
  } catch {
    errorReason.value = 'load-failed'
  }
}

async function load(): Promise<void> {
  sourceUrl.value = ''
  textContent.value = ''
  errorReason.value = ''
  retried.value = false
  zoom.value = 1
  rotation.value = 0
  const file = current.value
  if (!file || !props.ready) {
    return
  }
  if (kind.value === 'other') {
    errorReason.value = 'unsupported'
    emit('error', { file, reason: 'unsupported' })
    return
  }
  if (file.url) {
    sourceUrl.value = file.url
    if (kind.value === 'text') {
      await loadText(file.url)
    }
    return
  }
  if (props.presignedFetcher) {
    presigned.setFetcher(() => props.presignedFetcher?.(file) as Promise<PresignedResult>)
    const url = await presigned.get()
    if (url) {
      sourceUrl.value = url
      if (kind.value === 'text') {
        await loadText(url)
      }
    } else {
      errorReason.value = 'expired'
    }
    return
  }
  errorReason.value = 'expired'
}

watch([() => props.index, () => props.files, () => props.ready], () => void load(), { immediate: true })

async function handleMediaError(): Promise<void> {
  const file = current.value
  if (!file) {
    return
  }
  if (!retried.value && props.presignedFetcher) {
    retried.value = true
    sourceUrl.value = ''
    presigned.refresh()
    const url = await presigned.get()
    if (url) {
      sourceUrl.value = url
      return
    }
  }
  errorReason.value = 'load-failed'
  emit('error', { file, reason: 'load-failed' })
}

function go(delta: number): void {
  const next = props.index + delta
  if (next < 0 || next >= props.files.length) {
    return
  }
  emit('update:index', next)
  const file = props.files[next]
  if (file) {
    emit('change', file, next)
  }
}

function close(): void {
  emit('update:visible', false)
  emit('close')
}

function download(): void {
  const file = current.value
  if (!file) {
    return
  }
  emit('download', file)
  if (sourceUrl.value !== '') {
    triggerDownload({ url: sourceUrl.value, filename: file.name })
  }
}

/** PDF 当前页码（1 起）。 */
const pdfPage = ref(1)
/** PDF 总页数（浏览器内置阅读器不可得时为 0，仅显示当前页）。 */
const pdfTotal = ref(0)

/** 带页码片段的 PDF 地址（`#page=N`，浏览器内置阅读器支持）。 */
const pdfUrl = computed(() => {
  if (sourceUrl.value === '') {
    return ''
  }
  return `${sourceUrl.value}#page=${pdfPage.value}`
})

/**
 * PDF 翻页。
 *
 * @param delta 页偏移（+1 / -1）。
 */
function turnPage(delta: number): void {
  const next = pdfPage.value + delta
  if (next < 1 || (pdfTotal.value > 0 && next > pdfTotal.value)) {
    return
  }
  pdfPage.value = next
}

/** 图片缩略图（多图切换）。 */
const imageFiles = computed(() => props.files.filter((file) => (file.mimeType ?? '').startsWith('image/')))

/**
 * 键盘操作：← / → 切换文件，Esc 关闭（仅可见时生效）。
 *
 * @param event 键盘事件。
 */
function onKeydown(event: KeyboardEvent): void {
  if (!props.visible) {
    return
  }
  if (event.key === 'Escape') {
    close()
  } else if (event.key === 'ArrowLeft') {
    go(-1)
  } else if (event.key === 'ArrowRight') {
    go(1)
  }
}

let offKeydown: () => void = () => {}

watch(
  () => props.visible,
  (visible) => {
    offKeydown()
    if (visible) {
      offKeydown = onGlobalKeydown(onKeydown)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => offKeydown())
</script>

<template>
  <div
    v-if="visible"
    class="bms-file-preview"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-kind="kind"
    :data-mode="mode"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div v-if="current" class="bms-file-preview__body" data-test="preview-body">
        <div class="bms-file-preview__header" data-test="preview-header">
          <span class="bms-file-preview__name" data-test="file-name">{{ current.name }}</span>
          <span class="bms-file-preview__meta" data-test="file-kind">
            {{ kind }} · {{ index + 1 }}/{{ files.length }}
          </span>
        </div>
        <slot name="live" :file="current" :kind="kind">
          <div class="bms-file-preview__stage" :data-kind="kind" data-test="stage">
            <div v-if="errorReason !== ''" class="bms-file-preview__error" data-test="preview-error">
              {{ errorText }}
            </div>
            <img
              v-else-if="kind === 'image' && sourceUrl !== ''"
              class="bms-file-preview__image"
              :src="sourceUrl"
              :alt="current.name"
              :style="imageStyle"
              data-test="preview-image"
              @error="handleMediaError"
            />
            <video
              v-else-if="kind === 'video' && sourceUrl !== ''"
              class="bms-file-preview__video"
              :src="sourceUrl"
              controls
              data-test="preview-video"
              @error="handleMediaError"
            />
            <audio
              v-else-if="kind === 'audio' && sourceUrl !== ''"
              class="bms-file-preview__audio"
              :src="sourceUrl"
              controls
              data-test="preview-audio"
              @error="handleMediaError"
            />
            <iframe
              v-else-if="kind === 'pdf' && sourceUrl !== ''"
              class="bms-file-preview__pdf"
              :src="pdfUrl"
              title="PDF 预览"
              data-test="preview-pdf"
            />
            <pre v-else-if="kind === 'text'" class="bms-file-preview__text" data-test="preview-text">{{ textContent }}</pre>
            <div v-else class="bms-file-preview__loading" data-test="preview-loading">加载中…</div>
          </div>
        </slot>

        <div v-if="kind === 'image' && thumbs && imageFiles.length > 1" class="bms-file-preview__thumbs" data-test="thumbs">
          <img
            v-for="file in imageFiles"
            :key="file.id"
            class="bms-file-preview__thumb"
            :class="{ 'is-active': file.id === current.id }"
            :src="file.url ?? ''"
            :alt="file.name"
            :data-test="`thumb-${file.id}`"
            @click="go(files.indexOf(file) - index)"
          />
        </div>

        <div class="bms-file-preview__toolbar">
          <el-button size="small" data-test="prev" :disabled="index <= 0" @click="go(-1)">上一张</el-button>
          <el-button size="small" data-test="next" :disabled="index >= files.length - 1" @click="go(1)">
            下一张
          </el-button>
          <template v-if="kind === 'image' && sourceUrl !== ''">
            <el-button size="small" data-test="zoom-in" @click="zoom += 0.2">放大</el-button>
            <el-button size="small" data-test="zoom-out" @click="zoom = Math.max(0.2, zoom - 0.2)">缩小</el-button>
            <el-button size="small" data-test="rotate" @click="rotation += 90">旋转</el-button>
          </template>
          <template v-if="kind === 'pdf' && sourceUrl !== ''">
            <el-button size="small" data-test="pdf-prev" :disabled="pdfPage <= 1" @click="turnPage(-1)">上一页</el-button>
            <span class="bms-file-preview__page" data-test="pdf-page">
              第 {{ pdfPage }} 页<template v-if="pdfTotal > 0"> / {{ pdfTotal }}</template>
            </span>
            <el-button
              size="small"
              data-test="pdf-next"
              :disabled="pdfTotal > 0 && pdfPage >= pdfTotal"
              @click="turnPage(1)"
            >
              下一页
            </el-button>
          </template>
          <el-button size="small" data-test="download" @click="download">下载</el-button>
          <el-button size="small" type="primary" data-test="close" @click="close">关闭</el-button>
        </div>
      </div>
      <div v-else class="bms-file-preview__empty" data-test="empty">
        <slot name="empty">暂无文件</slot>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-file-preview {
  box-sizing: border-box;
  color: var(--bms-color-text);
}

.bms-file-preview[data-mode='overlay'] {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  background: var(--bms-file-preview-mask-bg);
}

.bms-file-preview[data-mode='drawer'] {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 3000;
  width: 640px;
  max-width: 100%;
  background: var(--bms-color-bg);
  box-shadow: var(--bms-shadow-md);
}

.bms-file-preview[data-mode='inline'] {
  position: relative;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-file-preview__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.bms-file-preview__header {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--bms-space-3);
  padding: var(--bms-space-2) var(--bms-space-4);
  font-size: var(--bms-font-size-sm);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-file-preview[data-mode='overlay'] .bms-file-preview__header,
.bms-file-preview[data-mode='overlay'] .bms-file-preview__toolbar {
  color: var(--bms-color-text-inverse);
  border-color: var(--bms-color-border);
}

.bms-file-preview__name {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-file-preview__meta {
  flex: none;
  color: var(--bms-color-text-secondary);
}

.bms-file-preview__stage {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  min-height: 0;
  padding: var(--bms-space-4);
  overflow: hidden;
}

.bms-file-preview__image,
.bms-file-preview__video {
  max-width: 100%;
  max-height: 100%;
  transition: transform 0.12s ease;
}

.bms-file-preview__audio,
.bms-file-preview__pdf {
  width: 100%;
  height: 100%;
  min-height: 320px;
  border: 0;
}

.bms-file-preview__text {
  width: 100%;
  max-height: 100%;
  margin: 0;
  padding: var(--bms-space-3);
  overflow: auto;
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text);
  background: var(--bms-color-fill);
  border-radius: var(--bms-radius-md);
}

.bms-file-preview__error,
.bms-file-preview__loading,
.bms-file-preview__empty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  text-align: center;
}

.bms-file-preview__error {
  color: var(--bms-color-danger);
}

.bms-file-preview__empty {
  padding: var(--bms-space-8);
}

.bms-file-preview__thumbs {
  display: flex;
  flex: none;
  gap: var(--bms-space-1);
  padding: var(--bms-space-2) var(--bms-space-4);
  overflow-x: auto;
}

.bms-file-preview__thumb {
  width: 56px;
  height: 42px;
  cursor: pointer;
  object-fit: cover;
  border: 2px solid transparent;
  border-radius: var(--bms-radius-sm);
}

.bms-file-preview__thumb.is-active {
  border-color: var(--bms-color-primary);
}

.bms-file-preview__toolbar {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-2) var(--bms-space-4);
  border-top: 1px solid var(--bms-color-border);
}

.bms-file-preview__page {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

@media (max-width: 768px) {
  .bms-file-preview[data-mode='drawer'] {
    width: 100%;
  }
}
</style>

