/** 富文本编辑器投影：TipTap 内核投影（`@tiptap/*` 第三方库单一落点，件内不得直引）。 */
import { EditorContent, useEditor } from '@tiptap/vue-3';
import StarterKit from '@tiptap/starter-kit';
import { onBeforeUnmount } from 'vue';
import { useRichTextKernel } from './useRichTextKernel';
import { sanitizeHtml } from '../utils/sanitizeHtml';
/**
 * 使用富文本编辑器投影。
 *
 * @param options 选项。
 * @returns 编辑器实例、内容组件与只读切换。
 */
export function useRichTextEditor(options) {
    const { setReadOnly } = useRichTextKernel();
    const editor = useEditor({
        content: sanitizeHtml(options.content),
        editable: !(options.readOnly ?? false),
        extensions: [StarterKit],
        onUpdate: ({ editor: instance }) => {
            options.onUpdate(sanitizeHtml(instance.getHTML()));
        },
    });
    onBeforeUnmount(() => {
        editor.value?.destroy();
    });
    return { editor, content: EditorContent, setReadOnly };
}
