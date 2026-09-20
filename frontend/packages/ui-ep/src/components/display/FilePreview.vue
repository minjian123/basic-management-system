<script setup lang="ts">
// 文件预览（07_03）：类型分发（图片 / PDF / 音视频 / 文本 / 其他降级下载）、预签名获取与失效重取、下载。
import { computed, ref, watch } from 'vue'

import { useBasePresignedUrl } from '../../composables/useBasePresignedUrl'
import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'
import { triggerDownload } from '../../utils/downloadFile'
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
</script>

<template>
  <div
    v-if="visible"
    class="bms-file-preview"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-kind="kind"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div v-if="current" class="bms-file-preview__body" data-test="preview-body">
        <slot name="live" :file="current" :kind="kind">
          <div class="bms-file-preview__stage" :data-kind="kind" data-test="stage">
            <div v-if="errorReason !== ''" class="bms-file-preview__error" data-test="preview-error">
              {{ errorText }}
            </div>
            <img
              v-else-if="kind === 'image' && sourceUrl !== ''"
              :src="sourceUrl"
              :alt="current.name"
              :style="imageStyle"
              data-test="preview-image"
              @error="handleMediaError"
            />
            <video
              v-else-if="kind === 'video' && sourceUrl !== ''"
              :src="sourceUrl"
              controls
              data-test="preview-video"
              @error="handleMediaError"
            />
            <audio
              v-else-if="kind === 'audio' && sourceUrl !== ''"
              :src="sourceUrl"
              controls
              data-test="preview-audio"
              @error="handleMediaError"
            />
            <iframe
              v-else-if="kind === 'pdf' && sourceUrl !== ''"
              :src="sourceUrl"
              title="PDF 预览"
              data-test="preview-pdf"
            />
            <pre v-else-if="kind === 'text'" data-test="preview-text">{{ textContent }}</pre>
            <div v-else data-test="preview-loading">加载中…</div>
          </div>
        </slot>
        <div class="bms-file-preview__toolbar">
          <button type="button" data-test="prev" :disabled="index <= 0" @click="go(-1)">上一张</button>
          <span data-test="file-name">{{ current.name }}</span>
          <button type="button" data-test="next" :disabled="index >= files.length - 1" @click="go(1)">下一张</button>
          <template v-if="kind === 'image' && sourceUrl !== ''">
            <button type="button" data-test="zoom-in" @click="zoom += 0.2">放大</button>
            <button type="button" data-test="zoom-out" @click="zoom = Math.max(0.2, zoom - 0.2)">缩小</button>
            <button type="button" data-test="rotate" @click="rotation += 90">旋转</button>
          </template>
          <button type="button" data-test="download" @click="download">下载</button>
          <button type="button" data-test="close" @click="close">关闭</button>
        </div>
      </div>
      <div v-else class="bms-file-preview__empty" data-test="empty">
        <slot name="empty">暂无文件</slot>
      </div>
    </template>
  </div>
</template>
