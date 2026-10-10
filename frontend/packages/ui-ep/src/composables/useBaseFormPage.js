/** 表单页投影：把核心表单页组合能力基类 `BaseFormPage` 投影为组合式（三态 / 脏数据 / 提交）。 */
import { BaseFormPage } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体表单页（可实例化）。 */
class FormPageState extends BaseFormPage {
}
/**
 * 使用表单页投影。
 *
 * @param options 选项。
 * @returns 表单页基类实例与响应式面。
 */
export function useBaseFormPage(options = {}) {
    const page = new FormPageState();
    if (options.mode !== undefined) {
        page.mode = options.mode;
    }
    if (options.submitter !== undefined) {
        page.submitter = options.submitter;
    }
    const mode = ref(page.mode);
    const dirty = ref(page.dirty);
    const off = page.onLifecycle((event) => {
        if (event === 'update') {
            mode.value = page.mode;
            dirty.value = page.dirty;
        }
    });
    onScopeDispose(off);
    return {
        page,
        mode,
        dirty,
        setMode: (next) => {
            page.setMode(next);
            page.notifyLifecycle('update');
        },
        markDirty: (next = true) => {
            page.markDirty(next);
            page.notifyLifecycle('update');
        },
        submit: async () => {
            await page.submit();
            page.notifyLifecycle('update');
        },
        shouldConfirmBack: () => page.back(),
    };
}
