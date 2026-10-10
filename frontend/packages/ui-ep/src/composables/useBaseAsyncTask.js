/** 异步任务投影：把核心异步任务能力基类 `BaseAsyncTask` 投影为组合式（提交 / 进度 / 取消 / 结果）。 */
import { BaseAsyncTask } from '@bms/core';
import { onScopeDispose, ref, shallowRef } from 'vue';
/** 具体异步任务（可实例化）。 */
class AsyncTask extends BaseAsyncTask {
}
/**
 * 使用异步任务投影。
 *
 * @param options 选项。
 * @returns 异步任务基类实例与响应式面。
 */
export function useBaseAsyncTask(options = {}) {
    const task = new AsyncTask();
    if (options.pollInterval !== undefined) {
        task.pollInterval = options.pollInterval;
    }
    const status = ref(task.status);
    const progress = shallowRef(task.progress);
    const sync = () => {
        status.value = task.status;
        progress.value = task.progress;
    };
    const off = task.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        task,
        status,
        progress,
        result: () => task.result,
        submit: async () => {
            await task.submit();
            sync();
        },
        cancel: () => {
            task.cancel();
        },
        nextPollDelay: (attempt) => task.nextPollDelay(attempt),
    };
}
