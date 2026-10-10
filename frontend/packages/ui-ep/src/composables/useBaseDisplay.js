/** 展示件投影：把核心展示组件基类 `BaseDisplay` 投影为组合式（值 / 空态）。 */
import { BaseDisplay } from '@bms/core';
import { onScopeDispose, ref, shallowRef } from 'vue';
/** 具体展示件（可实例化）。 */
class DisplayState extends BaseDisplay {
}
/**
 * 使用展示件投影。
 *
 * @returns 展示基类实例与响应式面。
 */
export function useBaseDisplay() {
    const display = new DisplayState();
    const value = shallowRef(display.value);
    const isEmpty = ref(display.isEmpty);
    display.onChange((next) => {
        value.value = next;
    });
    const off = display.onLifecycle((event) => {
        if (event === 'update') {
            value.value = display.value;
            isEmpty.value = display.isEmpty;
        }
    });
    onScopeDispose(off);
    return {
        display,
        value,
        isEmpty,
        setValue: (next) => display.setValue(next),
    };
}
