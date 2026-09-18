<script setup lang="ts">
// 富文本字段（06_03）：富文本 / 源码双模式 + 白名单双向清洗 + 只读渲染 + 内核经 `BaseEditorKernel`。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useRichTextKernel } from '../../composables/useRichTextKernel'
import { sanitizeHtml, sanitizeToText } from '../../utils/sanitizeHtml'

// 编辑器内核独立分包（TipTap 不进首屏 / 基础分包）。
const RichTextEditor = defineAsyncComponent(() => import('./RichTextEditor.vue'))

/** 展示模式。 */
export type RichTextFieldMode = 'rich' | 'source'

interface Props {
  /** 内容（已清洗 HTML）。 */
  modelValue?: string
  /** 模式。 */
  mode?: RichTextFieldMode
  /** 只读。 */
  readOnly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 最小高度。 */
  minHeight?: string
  /** 最大字数（净化后纯文本）。 */
  maxLength?: number
  /** 图片上传（缺省降级）。 */
  uploadImage?: (file: File) => Promise<string>
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  mode: 'rich',
  readOnly: false,
  placeholder: '请输入内容',
  minHeight: '160px',
  maxLength: undefined,
  uploadImage: undefined,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  invalid: [message: string]
  'upload-error': [reason: string]
}>()

const { setMode } = useRichTextKernel({ mode: props.mode === 'source' ? 'code' : 'rich' })
const content = ref(sanitizeHtml(props.modelValue))
const lengthError = ref('')

watch(
  () => props.modelValue,
  (next) => {
    content.value = sanitizeHtml(next)
  },
)

watch(
  () => props.mode,
  (next) => setMode(next === 'source' ? 'code' : 'rich'),
)

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : lengthError.value))

/** 纯文本长度。 */
const textLength = computed(() => sanitizeToText(content.value).length)

function commit(next: string): void {
  const cleaned = sanitizeHtml(next)
  if (props.maxLength !== undefined && sanitizeToText(cleaned).length > props.maxLength) {
    lengthError.value = `最多 ${props.maxLength} 字`
    emit('invalid', lengthError.value)
    return
  }
  lengthError.value = ''
  content.value = cleaned
  emit('update:modelValue', cleaned)
  emit('change', cleaned)
}

function onRichUpdate(next: string): void {
  commit(next)
}

function onSourceInput(event: Event): void {
  commit((event.target as HTMLTextAreaElement).value)
}

/**
 * 上传图片并插入（缺省降级）。
 *
 * @param file 图片文件。
 */
async function uploadAndInsert(file: File): Promise<string | undefined> {
  if (props.uploadImage === undefined) {
    emit('upload-error', '上传未就绪')
    return undefined
  }
  try {
    const url = await props.uploadImage(file)
    commit(`${content.value}<img src="${url}" alt="" />`)
    return url
  } catch {
    emit('upload-error', '上传失败')
    return undefined
  }
}

defineExpose({ uploadAndInsert, textLength })
</script>

<template>
  <div
    class="bms-rich-text-field"
    :data-mode="mode"
    :data-invalid="resolvedError !== ''"
    :style="{ minHeight }"
  >
    <!-- 内容已经 `sanitizeHtml` 白名单清洗，此处渲染为受控 HTML。 -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="readOnly" class="bms-rich-text-field__readonly" data-test="rich-readonly" v-html="content" />

    <template v-else>
      <rich-text-editor
        v-if="mode === 'rich'"
        :model-value="content"
        :read-only="false"
        :placeholder="placeholder"
        @update:model-value="onRichUpdate"
      />
      <textarea
        v-else
        class="bms-rich-text-field__source"
        data-test="rich-source"
        :value="content"
        :placeholder="placeholder"
        @input="onSourceInput"
      />
    </template>

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
