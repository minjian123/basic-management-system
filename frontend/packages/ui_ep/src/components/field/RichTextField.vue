<script setup lang="ts">
// 富文本字段（06_03）：富文本 / 源码双模式 + 白名单双向清洗 + 只读统一排版渲染 + 内核经 `BaseEditorKernel`。
// 只读态：按标题层级 / 表格 / 代码块 / 引用 / 图片自适应统一排版；`pre > code` 按 `language-*` 白名单高亮。
// 内核能力（工具栏档位 / 内容开关 / 目录导航 / 轻 Markdown 实时预览 / 附件卡片 / 公式）见详细设计 §9，登记遗留。
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'

import { useRichTextKernel } from '../../composables/useRichTextKernel'
import TextareaInput from '../input/TextareaInput.vue'
import { highlightCode } from '../../composables/useHighlight'
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
  focus: []
  blur: []
}>()

const { setMode } = useRichTextKernel({ mode: props.mode === 'source' ? 'code' : 'rich' })
const content = ref(sanitizeHtml(props.modelValue, 'richtext'))
const lengthError = ref('')

watch(
  () => props.modelValue,
  (next) => {
    content.value = sanitizeHtml(next, 'richtext')
  },
)

watch(
  () => props.mode,
  (next) => setMode(next === 'source' ? 'code' : 'rich'),
)

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : lengthError.value))

/** 纯文本长度。 */
const textLength = computed(() => sanitizeToText(content.value).length)

/** 字数统计文本（节点 §6「其他」：字数统计）。 */
const lengthText = computed(() =>
  props.maxLength === undefined ? `${textLength.value} 字` : `${textLength.value} / ${props.maxLength} 字`,
)

/** 只读态是否为空（空值占位——节点 §9）。 */
const isEmpty = computed(() => sanitizeToText(content.value).trim() === '')

/** 只读态渲染用 HTML（代码块按 `language-*` 白名单高亮后回填）。 */
const renderedHtml = ref(content.value)

/**
 * 对只读 HTML 内的 `pre > code.language-*` 逐块高亮（节点 §4/§6：只读按语言类名高亮，语言限定白名单）。
 */
async function highlightBlocks(): Promise<void> {
  const html = content.value
  if (!html.includes('language-')) {
    renderedHtml.value = html
    return
  }
  const matches = [...html.matchAll(/<code class="language-([a-z0-9+#-]+)">([\s\S]*?)<\/code>/gi)]
  let result = html
  for (const match of matches) {
    const [whole, language, body] = match
    const code = body
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&amp;/g, '&')
    const highlighted = await highlightCode(code, language)
    result = result.replace(whole, `<code class="language-${language}">${highlighted}</code>`)
  }
  renderedHtml.value = result
}

watch(content, () => {
  void highlightBlocks()
})

onMounted(() => {
  void highlightBlocks()
})

function commit(next: string): void {
  const cleaned = sanitizeHtml(next, 'richtext')
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
    <!-- 内容已经 `sanitizeHtml`（richtext 档）白名单清洗，此处渲染为受控 HTML。 -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="readOnly" class="bms-rich-text-field__readonly" data-test="rich-readonly">
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div v-if="!isEmpty" class="bms-rich-text-field__content" v-html="renderedHtml" />
      <span v-else class="bms-rich-text-field__empty" data-test="rich-empty">暂无内容</span>
    </div>

    <template v-else>
      <rich-text-editor
        v-if="mode === 'rich'"
        :model-value="content"
        :read-only="false"
        :placeholder="placeholder"
        @update:model-value="onRichUpdate"
      />
      <textarea-input
        v-else
        class="bms-rich-text-field__source"
        data-test="rich-source"
        :model-value="content"
        :placeholder="placeholder"
        :rows="6"
        @update:model-value="commit"
        @focus="emit('focus')"
        @blur="emit('blur')"
      />
    </template>

    <p v-if="!readOnly" class="bms-rich-text-field__count" data-test="rich-count">{{ lengthText }}</p>
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-rich-text-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

/* 编辑态内容区（内核宿主）外框。 */
.bms-rich-text-field :deep(.bms-rich-text-editor) {
  border: 1px solid var(--bms-richtext-border);
  border-radius: var(--bms-radius-md);
  overflow: hidden;
}

.bms-rich-text-field__source {
  box-sizing: border-box;
  width: 100%;
  padding: var(--bms-space-2) var(--bms-space-3);
  color: var(--bms-color-text);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-sm);
  line-height: var(--bms-line-height);
  background: var(--bms-richtext-content-bg);
  border: 1px solid var(--bms-richtext-border);
  border-radius: var(--bms-radius-md);
  resize: vertical;
}

.bms-rich-text-field__count {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  text-align: right;
}

/* ── 只读统一排版（节点 §2/§9）──────────────────────────────────────────── */
.bms-rich-text-field__readonly {
  padding: var(--bms-space-2) var(--bms-space-3);
  color: var(--bms-color-text);
  background: var(--bms-richtext-content-bg);
  border: 1px solid var(--bms-richtext-border);
  border-radius: var(--bms-radius-md);
}

.bms-rich-text-field__empty {
  color: var(--bms-color-text-secondary);
}

.bms-rich-text-field__content :deep(h1),
.bms-rich-text-field__content :deep(h2),
.bms-rich-text-field__content :deep(h3),
.bms-rich-text-field__content :deep(h4) {
  margin: var(--bms-space-3) 0 var(--bms-space-2);
  font-weight: 600;
  line-height: 1.35;
}

.bms-rich-text-field__content :deep(h1) {
  font-size: var(--bms-font-size-lg);
}

.bms-rich-text-field__content :deep(h2),
.bms-rich-text-field__content :deep(h3),
.bms-rich-text-field__content :deep(h4) {
  font-size: var(--bms-font-size);
}

.bms-rich-text-field__content :deep(p) {
  margin: 0 0 var(--bms-space-2);
}

.bms-rich-text-field__content :deep(blockquote) {
  margin: var(--bms-space-2) 0;
  padding: var(--bms-space-1) var(--bms-space-3);
  color: var(--bms-color-text-secondary);
  border-left: 3px solid var(--bms-richtext-border);
}

.bms-rich-text-field__content :deep(pre) {
  margin: var(--bms-space-2) 0;
  padding: var(--bms-space-2) var(--bms-space-3);
  overflow-x: auto;
  background: var(--bms-richtext-code-bg);
  border: 1px solid var(--bms-richtext-border);
  border-radius: var(--bms-radius-md);
}

.bms-rich-text-field__content :deep(pre code) {
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-sm);
}

.bms-rich-text-field__content :deep(code) {
  padding: 0 var(--bms-space-1);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-sm);
  background: var(--bms-richtext-code-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-rich-text-field__content :deep(table) {
  width: 100%;
  margin: var(--bms-space-2) 0;
  border-collapse: collapse;
  table-layout: auto;
}

.bms-rich-text-field__content :deep(th),
.bms-rich-text-field__content :deep(td) {
  padding: var(--bms-space-1) var(--bms-space-2);
  border: 1px solid var(--bms-richtext-border);
  text-align: left;
}

.bms-rich-text-field__content :deep(th) {
  background: var(--bms-richtext-toolbar-bg);
  font-weight: 600;
}

.bms-rich-text-field__content :deep(img) {
  max-width: 100%;
  height: auto;
}

.bms-rich-text-field__content :deep(a) {
  color: var(--bms-color-primary);
}

.bms-rich-text-field__content :deep(ul),
.bms-rich-text-field__content :deep(ol) {
  margin: 0 0 var(--bms-space-2);
  padding-left: var(--bms-space-6);
}

.bms-rich-text-field__content :deep(hr) {
  margin: var(--bms-space-3) 0;
  border: none;
  border-top: 1px solid var(--bms-richtext-border);
}
</style>
