/** 富文本编辑器投影：TipTap 内核投影（`@tiptap/*` 第三方库单一落点，件内不得直引）。 */

import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { onBeforeUnmount, type Component } from 'vue'

import { useRichTextKernel } from './useRichTextKernel'
import { sanitizeHtml } from '../utils/sanitizeHtml'

/** 选项。 */
export interface UseRichTextEditorOptions {
  /** 初始内容（已清洗 HTML）。 */
  content: string
  /** 只读。 */
  readOnly?: boolean
  /** 内容变更回调（已清洗 HTML）。 */
  onUpdate: (html: string) => void
}

/** `useRichTextEditor` 返回面。 */
export interface UseRichTextEditorResult {
  /** TipTap 编辑器实例（响应式）。 */
  editor: ReturnType<typeof useEditor>
  /** 编辑器内容渲染组件。 */
  content: Component
  /** 设置只读（经富文本内核投影）。 */
  setReadOnly: (readOnly: boolean) => void
}

/**
 * 使用富文本编辑器投影。
 *
 * @param options 选项。
 * @returns 编辑器实例、内容组件与只读切换。
 */
export function useRichTextEditor(options: UseRichTextEditorOptions): UseRichTextEditorResult {
  const { setReadOnly } = useRichTextKernel()
  const editor = useEditor({
    content: sanitizeHtml(options.content),
    editable: !(options.readOnly ?? false),
    extensions: [StarterKit],
    onUpdate: ({ editor: instance }) => {
      options.onUpdate(sanitizeHtml(instance.getHTML()))
    },
  })
  onBeforeUnmount(() => {
    editor.value?.destroy()
  })
  return { editor, content: EditorContent, setReadOnly }
}
