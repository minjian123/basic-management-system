/** 表单元数据投影：把核心表单元数据能力基类 `BaseFormMeta` 投影为组合式（加载 / 版本比对）。 */
import { BaseFormMeta } from '@bms/core';
import { onScopeDispose, ref, shallowRef } from 'vue';
/** 具体表单元数据件（可实例化）。 */
class FormMetaState extends BaseFormMeta {
}
/**
 * 使用表单元数据投影。
 *
 * @param options 选项。
 * @returns 表单元数据基类实例与响应式面。
 */
export function useBaseFormMeta(options = {}) {
    const formMeta = new FormMetaState();
    if (options.loader !== undefined) {
        formMeta.loader = options.loader;
    }
    const meta = shallowRef(formMeta.meta);
    const dataVersion = ref(formMeta.dataVersion);
    const sync = () => {
        meta.value = formMeta.meta;
        dataVersion.value = formMeta.dataVersion;
    };
    const off = formMeta.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        formMeta,
        meta,
        dataVersion,
        load: async () => {
            await formMeta.load();
            sync();
        },
        needsRefresh: (version) => formMeta.needsRefresh(version),
    };
}
