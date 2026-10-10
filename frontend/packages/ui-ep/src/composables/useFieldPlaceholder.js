/** 占位字段组合式：输入组件基类 `BaseInput`（经 `BaseField` → `BaseValue` → `BasePlaceholderState` 继承占位语义）的薄投影。 */
import { BaseInput } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体占位字段件（直接继承输入组件基类，占位语义经链上继承取得）。 */
class FieldPlaceholderState extends BaseInput {
}
/**
 * 使用占位字段降级语义。
 *
 * @param options 选项。
 * @returns 就绪 / 降级 / 禁用与请求计数。
 */
export function useFieldPlaceholder(options = {}) {
    const state = new FieldPlaceholderState();
    state.disabled = options.disabled ?? false;
    state.setReady(options.ready ?? false);
    const ready = ref(state.ready);
    const degraded = ref(state.degraded);
    const requestCount = ref(state.requestCount);
    const disabled = computed(() => state.disabled || !ready.value);
    const value = ref(state.value);
    state.onChange((next) => {
        value.value = next;
    });
    const off = state.onLifecycle((event) => {
        if (event === 'update') {
            ready.value = state.ready;
            degraded.value = state.degraded;
            requestCount.value = state.requestCount;
            value.value = state.value;
        }
    });
    onScopeDispose(() => {
        off();
        state.dispose();
    });
    return {
        ready,
        degraded,
        disabled,
        requestCount,
        setReady: (value) => state.setReady(value),
        markLoaded: () => state.markLoaded(),
        value,
        setValue: (value) => state.setValue(value),
    };
}
