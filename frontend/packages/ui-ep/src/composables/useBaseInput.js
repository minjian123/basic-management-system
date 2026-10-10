/** 输入件投影：把核心输入组件基类 `BaseInput` 投影为组合式（受控 / 三态 / 禁用合并 / 清空 / 焦点）。 */
import { BaseInput } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体输入件（可实例化）。 */
class InputState extends BaseInput {
}
/**
 * 使用输入件投影。
 *
 * @param options 选项。
 * @returns 输入基类实例与响应式面。
 */
export function useBaseInput(options = {}) {
    const input = new InputState();
    const localDisabled = ref(options.disabled ?? false);
    if (options.disabled !== undefined) {
        input.disabled = options.disabled;
    }
    if (options.loading !== undefined) {
        input.loading = options.loading;
    }
    if (options.placeholder !== undefined) {
        input.placeholder = options.placeholder;
    }
    if (options.clearable !== undefined) {
        input.clearable = options.clearable;
    }
    if (options.value !== undefined) {
        input.setValue(options.value);
    }
    const value = ref(input.value);
    const isEmpty = ref(input.isEmpty);
    const loading = ref(input.loading);
    const focused = ref(input.focused);
    const sizeToken = ref(input.size);
    const density = ref(input.density);
    const disabled = computed(() => localDisabled.value || input.disabled);
    input.onChange((next) => {
        value.value = next;
        isEmpty.value = input.isEmpty;
    });
    const off = input.onLifecycle((event) => {
        if (event === 'update') {
            value.value = input.value;
            isEmpty.value = input.isEmpty;
            loading.value = input.loading;
            focused.value = input.focused;
            sizeToken.value = input.size;
            density.value = input.density;
        }
    });
    onScopeDispose(off);
    return {
        input,
        value,
        isEmpty,
        disabled,
        loading,
        focused,
        sizeToken,
        density,
        setValue: (next) => input.setValue(next),
        clear: () => input.clear(),
        focus: () => input.focus(),
        blur: () => input.blur(),
        setDisabled: (next) => {
            localDisabled.value = next;
        },
        setLoading: (next) => {
            input.loading = next;
            input.notifyLifecycle('update');
        },
        onValueChange: (listener) => input.onChange(listener),
    };
}
