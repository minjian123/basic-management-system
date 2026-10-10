/** 占位展示组合式：展示组件基类 `BaseDisplay`（经 `BaseValue` → `BasePlaceholderState` 继承占位语义）的薄投影。 */
import { BaseDisplay } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体占位展示件（直接继承展示组件基类，占位语义经链上继承取得）。 */
class DisplayPlaceholderState extends BaseDisplay {
}
/**
 * 使用占位展示降级语义。
 *
 * @param options 选项。
 * @returns 就绪 / 降级与请求计数。
 */
export function useDisplayPlaceholder(options = {}) {
    const state = new DisplayPlaceholderState();
    if (options.value !== undefined) {
        state.setValue(options.value);
    }
    state.setReady(options.ready ?? false);
    const ready = ref(state.ready);
    const degraded = ref(state.degraded);
    const requestCount = ref(state.requestCount);
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
        requestCount,
        setReady: (value) => state.setReady(value),
        markLoaded: () => state.markLoaded(),
        value,
        setValue: (value) => state.setValue(value),
    };
}
