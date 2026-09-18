<script setup lang="ts">
// 导入对话框（占位版，08_01_02）：契约先行冻结；数据通路未就绪时不请求、操作禁用 + 降级提示。主体独立分包懒加载。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseUploadEngine } from '../../composables/useBaseUploadEngine'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 导入主体独立分包（上传 / 解析 / 错误行报告区，真实实现 08_05 接入）。
const ImportDialogBody = defineAsyncComponent(() => import('./ImportDialogBody.vue'))

/** 导入步骤。 */
export type ImportStep = 'select' | 'uploading' | 'result'

/** 导入结果（含错误行报告）。 */
export interface ImportResult {
  /** 总行数。 */
  total: number
  /** 成功行数。 */
  successCount: number
  /** 失败行数。 */
  failCount: number
  /** 错误行。 */
  errors: { row: number; column?: string; message: string }[]
}

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
  /** 降级文案。 */
  degradeText?: string
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
  degradeText: '导入未就绪（占位）',
})

const emit = defineEmits<{
  'update:visible': [visible: boolean]
  'download-template': [params: Record<string, unknown> | undefined]
  submit: [payload: { file: File; idempotencyKey: string }]
  retry: []
  'download-errors': []
  done: []
  reset: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { progress } = useBaseUploadEngine<File>({ maxSize: props.maxSize })

const step = ref<ImportStep>('select')
const file = ref<File | null>(null)
const fileName = ref('')
const fileError = ref('')
const result = ref<ImportResult | null>(null)
const idempotencyKey = ref('')

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

/** 提交是否禁用（占位 / 未选文件 / 文件校验失败）。 */
const submitDisabled = computed(
  () => placeholder.disabled.value || file.value === null || fileError.value !== '',
)

/** 生成幂等键（选定文件时生成，重试复用）。 */
function newKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/** 选择文件并做类型 / 大小校验。 */
function pickFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0]
  if (picked) {
    validateFile(picked)
  }
}

function validateFile(picked: File): void {
  file.value = null
  result.value = null
  fileName.value = picked.name
  const ext = `.${picked.name.split('.').pop()?.toLowerCase() ?? ''}`
  const accepted = props.accept
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter((item) => item !== '')
  if (accepted.length > 0 && !accepted.includes(ext)) {
    fileError.value = `仅支持 ${props.accept} 文件`
    return
  }
  if (props.maxSize > 0 && picked.size > props.maxSize) {
    fileError.value = `文件大小超过 ${Math.round(props.maxSize / 1024 / 1024)}MB`
    return
  }
  fileError.value = ''
  file.value = picked
  idempotencyKey.value = newKey()
}

/** 提交导入（占位：仅透传事件，不发请求）。 */
function submit(): void {
  if (submitDisabled.value || file.value === null) {
    return
  }
  step.value = 'uploading'
  emit('submit', { file: file.value, idempotencyKey: idempotencyKey.value })
}

/** 重新导入（回到选文件步并重置，新一次导入）。 */
function reset(): void {
  step.value = 'select'
  file.value = null
  fileName.value = ''
  fileError.value = ''
  result.value = null
  idempotencyKey.value = ''
  emit('reset')
}

/** 关闭对话框。 */
function close(): void {
  if (placeholder.disabled.value) {
    return
  }
  emit('update:visible', false)
}

/** 下载模板。 */
function downloadTemplate(): void {
  if (placeholder.disabled.value) {
    return
  }
  emit('download-template', props.templateParams)
}

/** 下载错误明细。 */
function downloadErrors(): void {
  if (placeholder.disabled.value) {
    return
  }
  emit('download-errors')
}
</script>

<template>
  <div
    class="bms-import-dialog"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <header class="bms-import-dialog__header" data-test="header">批量导入{{ bizName }}</header>
        <div class="bms-import-dialog__toolbar">
          <button type="button" data-test="template" :disabled="placeholder.disabled.value" @click="downloadTemplate">
            下载模板
          </button>
        </div>
        <input
          type="file"
          data-test="file-input"
          :accept="accept"
          :disabled="placeholder.disabled.value"
          @change="pickFile"
        />
        <span v-if="fileName" data-test="file-name">{{ fileName }}</span>
        <span v-if="fileError" data-test="file-error">{{ fileError }}</span>

        <component :is="ImportDialogBody" :step="step" :result="result" :progress="progress" />

        <footer class="bms-import-dialog__footer" data-test="footer">
          <button type="button" data-test="submit" :disabled="submitDisabled" @click="submit">提交</button>
          <button type="button" data-test="retry" :disabled="placeholder.disabled.value" @click="emit('retry')">
            重试
          </button>
          <button
            type="button"
            data-test="download-errors"
            :disabled="placeholder.disabled.value"
            @click="downloadErrors"
          >
            下载错误明细
          </button>
          <button type="button" data-test="reset" :disabled="placeholder.disabled.value" @click="reset">重新导入</button>
          <button type="button" data-test="close" :disabled="placeholder.disabled.value" @click="close">关闭</button>
        </footer>
      </slot>
    </template>
  </div>
</template>
