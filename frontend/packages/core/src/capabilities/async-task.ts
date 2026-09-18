/**
 * 异步任务能力基类：提交 / 轮询进度（退避）/ 取消 / 结果（执行器由宿主注入，占位不请求）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 任务状态。 */
export type TaskStatus = 'idle' | 'running' | 'done' | 'error' | 'canceled'

/** 任务进度。 */
export interface TaskProgress {
  /** 已完成量。 */
  value: number
  /** 总量（可选）。 */
  total?: number
  /** 进度说明。 */
  message?: string
}

/** 任务执行器（宿主注入；`report` 回传进度）。 */
export type TaskExecutor<TResult> = (report: (progress: TaskProgress) => void) => Promise<TResult>

/** 异步任务能力基类（抽象）。 */
export abstract class BaseAsyncTask<TResult = unknown> extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'async-task'
  /** 当前状态。 */
  status: TaskStatus = 'idle'
  /** 当前进度。 */
  progress: TaskProgress | undefined
  /** 轮询退避基数（毫秒）。 */
  pollInterval = 500
  /** 任务执行器（未注入则按占位：不动作）。 */
  executor: TaskExecutor<TResult> | undefined
  /** 结果。 */
  #result: TResult | undefined
  /** 是否已请求取消。 */
  #canceled = false

  /** 任务结果。 */
  get result(): TResult | undefined {
    return this.#result
  }

  /** 提交任务（未注入执行器则占位不动作）。 */
  async submit(): Promise<void> {
    if (this.executor === undefined) {
      return
    }
    this.#canceled = false
    this.status = 'running'
    this.notifyLifecycle('update')
    try {
      this.#result = await this.executor((progress) => {
        this.progress = progress
      })
      this.status = this.#canceled ? 'canceled' : 'done'
    } catch (error) {
      this.status = this.#canceled ? 'canceled' : 'error'
      this.reportError(error, { scope: 'BaseAsyncTask.submit' })
    }
    this.notifyLifecycle('update')
  }

  /** 请求取消。 */
  cancel(): void {
    this.#canceled = true
  }

  /**
   * 退避轮询间隔（指数退避，封顶 30 秒）。
   *
   * @param attempt 尝试次数（自 1 起）。
   */
  nextPollDelay(attempt: number): number {
    return Math.min(this.pollInterval * 2 ** Math.max(0, attempt - 1), 30_000)
  }
}
