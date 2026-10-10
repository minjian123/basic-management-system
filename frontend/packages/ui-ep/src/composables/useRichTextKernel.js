/** 富文本内核投影：把核心编辑器内核能力基类 `BaseEditorKernel` 投影为组合式（模式 / 只读）。 */
import { BaseEditorKernel } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体编辑器内核（可实例化）。 */
class RichTextKernel extends BaseEditorKernel {
}
/**
 * 使用富文本内核投影。
 *
 * @param options 选项。
 * @returns 内核基类实例与响应式面。
 */
export function useRichTextKernel(options = {}) {
    const kernel = new RichTextKernel();
    if (options.mode !== undefined) {
        kernel.mode = options.mode;
    }
    const mode = ref(kernel.mode);
    const readOnly = ref(options.readOnly ?? false);
    const off = kernel.onLifecycle((event) => {
        if (event === 'update') {
            mode.value = kernel.mode;
        }
    });
    onScopeDispose(off);
    return {
        kernel,
        mode,
        readOnly,
        setMode: (next) => {
            kernel.mode = next;
            kernel.notifyLifecycle('update');
        },
        setReadOnly: (next) => {
            readOnly.value = next;
        },
    };
}
