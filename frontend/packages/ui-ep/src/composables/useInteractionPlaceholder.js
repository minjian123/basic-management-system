/** 交互类占位组合式：数据状态能力基类 `BaseDataState`（经 `BasePlaceholderState` 继承占位语义）的薄投影。 */
import { BaseDataState } from '@bms/core';
import { computed, onScopeDispose, ref, watch } from 'vue';
/** 具体占位数据状态件（直接继承数据状态能力基类，占位语义经链上继承取得）。 */
class InteractionPlaceholderState extends BaseDataState {
}
/**
 * 使用交互件占位降级语义。
 *
 * @param options 选项。
 * @returns 就绪 / 降级 / 禁用与请求计数。
 */
export function useInteractionPlaceholder(options = {}) {
    const state = new InteractionPlaceholderState();
    state.setReady(options.ready ?? false);
    const ready = ref(state.ready);
    const degraded = ref(state.degraded);
    const requestCount = ref(state.requestCount);
    const currentState = ref(state.state);
    const disabled = computed(() => !ready.value);
    const off = state.onLifecycle((event) => {
        if (event === 'update') {
            ready.value = state.ready;
            degraded.value = state.degraded;
            requestCount.value = state.requestCount;
        }
    });
    const offState = state.onStateChange((next) => {
        currentState.value = next;
    });
    onScopeDispose(() => {
        off();
        offState();
        state.dispose();
    });
    watch(ready, (value) => {
        const token = state.begin();
        state.settle(token, value ? 'ready' : 'empty');
    }, { immediate: true, flush: 'sync' });
    return {
        ready,
        degraded,
        disabled,
        requestCount,
        state: currentState,
        dataState: state,
        setReady: (value) => state.setReady(value),
        markLoaded: () => state.markLoaded(),
        begin: () => state.begin(),
        settle: (token, next) => state.settle(token, next),
    };
}
