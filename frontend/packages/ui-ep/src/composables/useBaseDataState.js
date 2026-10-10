/** 数据状态投影：把核心数据状态能力基类 `BaseDataState` 投影为组合式（`loading → ready / empty / error` 状态机与竞态）。 */
import { BaseDataState } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体数据状态件（可实例化）。 */
class DataStateHolder extends BaseDataState {
}
/**
 * 使用数据状态投影。
 *
 * @returns 数据状态基类实例与响应式面。
 */
export function useBaseDataState() {
    const dataState = new DataStateHolder();
    const state = ref(dataState.state);
    const off = dataState.onStateChange((next) => {
        state.value = next;
    });
    onScopeDispose(off);
    return {
        dataState,
        state,
        begin: () => dataState.begin(),
        settle: (token, next) => dataState.settle(token, next),
        setState: (next) => {
            const token = dataState.begin();
            if (next !== 'loading') {
                dataState.settle(token, next);
            }
        },
    };
}
