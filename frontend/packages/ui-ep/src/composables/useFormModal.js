/** 弹窗表单组合式：打开 / 关闭 / 提交 / 重置 / 加载态（状态经核心 `BaseFormPage` 与 `BaseModalShell` 投影）。 */
import {} from '@bms/core';
import { ref } from 'vue';
import { useBaseFormPage } from './useBaseFormPage';
import { useModalShell } from './useModalShell';
/**
 * 弹窗表单组合式。
 *
 * @param options 选项。
 */
export function useFormModal(options = {}) {
    const shell = useModalShell();
    const title = ref('');
    const loading = ref(false);
    let pending;
    const form = useBaseFormPage({
        submitter: options.submit === undefined
            ? undefined
            : async () => {
                await options.submit?.(pending);
            },
    });
    function open(mode = 'create', nextTitle = '') {
        form.setMode(mode);
        form.markDirty(false);
        title.value = nextTitle;
        shell.open();
    }
    function close() {
        shell.close('close');
    }
    async function submit(values) {
        pending = values;
        loading.value = true;
        try {
            await form.submit();
            if (options.submit === undefined) {
                form.markDirty(false);
            }
        }
        finally {
            loading.value = false;
        }
    }
    return {
        visible: shell.visible,
        mode: form.mode,
        title,
        dirty: form.dirty,
        loading,
        open,
        close,
        reset: () => form.markDirty(false),
        markDirty: (dirty = true) => form.markDirty(dirty),
        submit,
    };
}
