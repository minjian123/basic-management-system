/** 异步任务投影：把核心异步任务能力基类 `BaseAsyncTask` 投影为组合式（提交 / 进度 / 取消 / 结果）。 */

import { BaseAsyncTask, type TaskProgress, type TaskStatus } from '@bms/core'
import { onScopeDispose, ref, shallowRef, type Ref } from 'vue'

/** 具体异步任务（可实例化）。 */
class AsyncTask<TResult> extends BaseAsyncTask<TResult> {}

/** 选项。 */
export interface UseBaseAsyncTaskOptions {
  /** 轮询退避基数（毫秒）。 */
  pollInterval?: number
}

/** `useBaseAsyncTask` 返回面。 */
export interface UseBaseAsyncTaskResult<TResult = unknown> {
  /** 异步任务基类实例。 */
  task: BaseAsyncTask<TResult>
  /** 任务状态（响应式）。 */
  status: Ref<TaskStatus>
  /** 任务进度（响应式）。 */
  progress: Ref<TaskProgress | undefined>
  /** 读取任务结果。 */
  result: () => TResult | undefined
  /** 提交任务（未注入执行器则占位不动作）。 */
  submit: () => Promise<void>
  /** 请求取消。 */
  cancel: () => void
  /** 退避轮询间隔（指数退避，封顶 30 秒）。 */
  nextPollDelay: (attempt: number) => number
}

/**
 * 使用异步任务投影。
 *
 * @param options 选项。
 * @returns 异步任务基类实例与响应式面。
 */
export function useBaseAsyncTask<TResult = unknown>(
  options: UseBaseAsyncTaskOptions = {},
): UseBaseAsyncTaskResult<TResult> {
  const task = new AsyncTask<TResult>()
  if (options.pollInterval !== undefined) {
    task.pollInterval = options.pollInterval
  }

  const status = ref<TaskStatus>(task.status)
  const progress = shallowRef<TaskProgress | undefined>(task.progress)
  const sync = (): void => {
    status.value = task.status
    progress.value = task.progress
  }
  const off = task.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    task,
    status,
    progress,
    result: () => task.result,
    submit: async () => {
      await task.submit()
      sync()
    },
    cancel: () => {
      task.cancel()
    },
    nextPollDelay: (attempt) => task.nextPollDelay(attempt),
  }
}
