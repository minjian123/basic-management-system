<script setup lang="ts">
// 富文本编辑器内核宿主（TipTap）：仅在 rich 模式挂载，避免源码模式加载内核。
import StarterKit from '@tiptap/starter-kit'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import { onBeforeUnmount, watch } from 'vue'

import { useRichTextKernel } from '../../composables/useRichTextKernel'
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

const { setReadOnly } = useRichTextKernel()

const editor = useEditor({
  content: sanitizeHtml(props.modelValue),
  editable: !props.readOnly,
  extensions: [StarterKit],
  onUpdate: ({ editor: instance }) => {
    emit('update:modelValue', sanitizeHtml(instance.getHTML()))
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

onBeforeUnmount(() => {
  editor.value?.destroy()
})

defineExpose({ editor })
</script>

<template>
  <editor-content class="bms-rich-text-editor" :editor="editor" />
</template>
