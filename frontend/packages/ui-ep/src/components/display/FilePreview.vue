<script setup lang="ts">
// 文件预览（占位版，07_01）：契约先行冻结；数据通路未就绪时不请求、降级提示。
import { computed, watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'

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
}

/** 预览失败原因。 */
export type PreviewErrorReason = 'expired' | 'unsupported' | 'load-failed' | 'forbidden'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 文件列表。 */
  files?: PreviewFile[]
  /** 当前索引。 */
  index?: number
  /** 是否显示。 */
  visible?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  files: () => [],
  index: 0,
  visible: true,
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

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

const current = computed<PreviewFile | undefined>(() => props.files[props.index])

const currentKind = computed<'image' | 'pdf' | 'other'>(() => {
  const mime = current.value?.mimeType ?? ''
  if (mime.startsWith('image/')) {
    return 'image'
  }
  if (mime === 'application/pdf') {
    return 'pdf'
  }
  return 'other'
})

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
</script>

<template>
  <div
    v-if="visible"
    class="bms-file-preview"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-kind="currentKind"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div v-if="current" class="bms-file-preview__body" data-test="preview-body">
        <slot name="live" :file="current" :kind="currentKind">
          <div class="bms-file-preview__stage" :data-kind="currentKind" data-test="stage">
            {{ current.name }}
          </div>
        </slot>
        <div class="bms-file-preview__toolbar">
          <button type="button" data-test="prev" :disabled="index <= 0" @click="go(-1)">上一张</button>
          <span data-test="file-name">{{ current.name }}</span>
          <button
            type="button"
            data-test="next"
            :disabled="index >= files.length - 1"
            @click="go(1)"
          >
            下一张
          </button>
          <button type="button" data-test="download" @click="emit('download', current)">下载</button>
          <button type="button" data-test="close" @click="close">关闭</button>
        </div>
      </div>
      <div v-else class="bms-file-preview__empty" data-test="empty">
        <slot name="empty">暂无文件</slot>
      </div>
    </template>
  </div>
</template>
