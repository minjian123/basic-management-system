/** 反馈组合式：基于核心 `BaseFeedback` 投影四态状态机与降级重试。 */
import { BaseFeedback } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体反馈件（可实例化）。 */
class Feedback extends BaseFeedback {
}
/**
 * 使用反馈组合式。
 *
 * @returns 反馈状态与操作方法。
 */
export function useFeedback() {
    const feedback = new Feedback();
    const state = ref(feedback.state);
    const off = feedback.onLifecycle((event) => {
        if (event === 'update') {
            state.value = feedback.state;
        }
    });
    onScopeDispose(off);
    return {
        state,
        begin: () => feedback.setState('loading'),
        ready: () => feedback.setState('ready'),
        empty: () => feedback.setState('empty'),
        error: () => feedback.setState('error'),
        setRetry: (retry) => {
            feedback.retry = retry;
        },
        retry: () => feedback.doRetry(),
    };
}
