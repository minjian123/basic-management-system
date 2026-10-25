<script setup lang="ts">
// 富文本编辑器内核宿主（TipTap）：仅在 rich 模式挂载，避免源码模式加载内核；TipTap 经投影单一落点。
// 占位经自绘层实现——TipTap Placeholder 扩展未在本工程依赖内，不新增依赖
// （工具栏与插件能力见详细设计 §9，登记遗留）。
import { computed, watch } from 'vue'

import { useRichTextEditor } from '../../composables/useRichTextEditor'
import { sanitizeHtml, sanitizeToText } from '../../utils/sanitizeHtml'

interface Props {
  /** 内容（已清洗 HTML）。 */
  modelValue: string
  /** 只读。 */
  readOnly?: boolean
  /** 占位提示。 */
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), { readOnly: false, placeholder: '' })

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { editor, content: RichTextContent, setReadOnly } = useRichTextEditor({
  content: props.modelValue,
  readOnly: props.readOnly,
  onUpdate: (html) => {
    emit('update:modelValue', html)
  },
})

watch(
  () => props.modelValue,
  (next) => {
    const instance = editor.value
    if (instance !== undefined && instance.getHTML() !== next) {
      instance.commands.setContent(sanitizeHtml(next, 'richtext'), { emitUpdate: false })
    }
  },
)

watch(
  () => props.readOnly,
  (next) => {
    setReadOnly(next)
    editor.value?.setEditable(!next)
  },
)

/** 内容是否为空（用于占位显示）。 */
const isEmpty = computed(() => sanitizeToText(props.modelValue).trim() === '')

/** 是否展示占位（编辑态且内容为空）。 */
const showPlaceholder = computed(() => !props.readOnly && isEmpty.value && props.placeholder !== '')

defineExpose({ editor })
</script>

<template>
  <div class="bms-rich-text-editor">
    <component :is="RichTextContent" class="bms-rich-text-editor__content" :editor="editor" />
    <span v-if="showPlaceholder" class="bms-rich-text-editor__placeholder" data-test="rich-placeholder">
      {{ placeholder }}
    </span>
  </div>
</template>

<style scoped>
.bms-rich-text-editor {
  position: relative;
  width: 100%;
  min-width: 0;
  color: var(--bms-color-text);
  background: var(--bms-richtext-content-bg);
}

.bms-rich-text-editor__content {
  min-height: 120px;
}

.bms-rich-text-editor__placeholder {
  position: absolute;
  top: var(--bms-space-2);
  left: var(--bms-space-3);
  color: var(--bms-color-text-secondary);
  pointer-events: none;
}

/* 内核内容区基础排版（工具条 / 目录 / 附件卡片等内核能力见详细设计 §9，登记遗留）。 */
.bms-rich-text-editor :deep(.ProseMirror) {
  min-height: 120px;
  padding: var(--bms-space-2) var(--bms-space-3);
  outline: none;
}

.bms-rich-text-editor :deep(.ProseMirror p) {
  margin: 0 0 var(--bms-space-2);
}
</style>
