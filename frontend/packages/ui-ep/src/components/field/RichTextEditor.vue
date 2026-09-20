<script setup lang="ts">
// 富文本编辑器内核宿主（TipTap）：仅在 rich 模式挂载，避免源码模式加载内核；TipTap 经投影单一落点。
import { watch } from 'vue'

import { useRichTextEditor } from '../../composables/useRichTextEditor'
import { sanitizeHtml } from '../../utils/sanitizeHtml'

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
      instance.commands.setContent(sanitizeHtml(next), { emitUpdate: false })
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

defineExpose({ editor })
</script>

<template>
  <component :is="RichTextContent" class="bms-rich-text-editor" :editor="editor" />
</template>
