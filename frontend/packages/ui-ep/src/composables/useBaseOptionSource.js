/** 选项源投影：把核心选项源能力基类 `BaseOptionSource` 投影为组合式（加载 / 版本比对 / 搜索回显）。 */
import { BaseOptionSource } from '@bms/core';
import { onScopeDispose, ref, shallowRef } from 'vue';
/** 具体选项源（可实例化）。 */
class OptionSourceState extends BaseOptionSource {
}
/**
 * 使用选项源投影。
 *
 * @param options 选项。
 * @returns 选项源基类实例与响应式面。
 */
export function useBaseOptionSource(options = {}) {
    const optionSource = new OptionSourceState();
    if (options.loader !== undefined) {
        optionSource.loader = options.loader;
    }
    const list = shallowRef([...optionSource.options]);
    const dataVersion = ref(optionSource.dataVersion);
    const sync = () => {
        list.value = [...optionSource.options];
        dataVersion.value = optionSource.dataVersion;
    };
    const off = optionSource.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        optionSource,
        options: list,
        dataVersion,
        load: async () => {
            await optionSource.load();
            sync();
        },
        getLabel: (value) => optionSource.getLabel(value),
        search: (keyword) => optionSource.search(keyword),
    };
}
