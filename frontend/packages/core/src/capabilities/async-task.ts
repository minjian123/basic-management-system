/**
 * 异步任务能力基类：提交 / 轮询进度（退避）/ 取消 / 结果（执行器由宿主注入，占位不请求）。
 *
 * 两种执行路径：**单段**（`executor` 一次执行并可回传进度）与**两段轮询**（`submitter` 提交 + `poller` 复查进度与结果，
 * 需二者同时注入）；两者皆未注入即占位不动作。**单段路径语义与扩展前逐字一致**。
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

/** 任务提交处理函数（两段轮询第一段；返回任务句柄）。 */
export type TaskSubmitter<THandle = unknown> = () => Promise<THandle>

/** 轮询结果（一次复查）。 */
export interface TaskPollOutcome<TResult> {
  /** 是否已完成。 */
  done: boolean
  /** 本次复查的进度（可选）。 */
  progress?: TaskProgress
  /** 完成时的结果（`done` 为真时消费）。 */
  result?: TResult
}

/** 任务轮询处理函数（两段轮询第二段：按句柄复查进度与结果）。 */
export type TaskPoller<THandle = unknown, TResult = unknown> = (
  handle: THandle,
  attempt: number,
) => Promise<TaskPollOutcome<TResult>>

/** 任意句柄的任务轮询处理函数（收敛签名长度）。 */
type AnyTaskPoller<TResult> = TaskPoller<unknown, TResult>

/**
 * 延时等待（轮询间隔）。
 *
 * @param ms 毫秒。
 */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

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
  /** 任务执行器（单段路径；未注入则按占位：不动作）。 */
  executor: TaskExecutor<TResult> | undefined
  /** 任务提交处理函数（与 `poller` 同时注入才走两段轮询路径）。 */
  submitter: TaskSubmitter | undefined
  /** 任务轮询处理函数（与 `submitter` 同时注入才走两段轮询路径）。 */
  poller: TaskPoller<unknown, TResult> | undefined
  /** 中断钩子（宿主注入；`cancel()` 时调用）。 */
  abort: (() => void) | undefined
  /** 结果。 */
  #result: TResult | undefined
  /** 是否已请求取消。 */
  #canceled = false

  /** 任务结果。 */
  get result(): TResult | undefined {
    return this.#result
  }

  /**
   * 提交任务。
   *
   * `submitter` 与 `poller` 同时注入 → 两段轮询；否则 `executor` 注入 → 单段执行；两者皆无则占位不动作。
   *
   * @returns 完成后的 `Promise`（占位时立即完成）。
   */
  async submit(): Promise<void> {
    if (this.submitter !== undefined && this.poller !== undefined) {
      await this.runPolled(this.submitter, this.poller)
      return
    }
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

  /** 请求取消（中断在途请求；单段路径在等待返回后置取消态，两段路径在下一轮复查前退出）。 */
  cancel(): void {
    this.#canceled = true
    this.abort?.()
  }

  /**
   * 退避轮询间隔（指数退避，封顶 30 秒）。
   *
   * @param attempt 尝试次数（自 1 起）。
   */
  nextPollDelay(attempt: number): number {
    return Math.min(this.pollInterval * 2 ** Math.max(0, attempt - 1), 30_000)
  }

  /**
   * 两段轮询执行（提交 → 轮询 → 结果）。
   *
   * @param submitter 提交处理函数。
   * @param poller 轮询处理函数。
   */
  private async runPolled(submitter: TaskSubmitter, poller: AnyTaskPoller<TResult>): Promise<void> {
    this.#canceled = false
    this.status = 'running'
    this.notifyLifecycle('update')
    try {
      const handle = await submitter()
      let attempt = 1
      for (;;) {
        if (this.#canceled) {
          this.status = 'canceled'
          this.notifyLifecycle('update')
          return
        }
        const outcome = await poller(handle, attempt)
        if (outcome.progress !== undefined) {
          this.progress = outcome.progress
        }
        this.notifyLifecycle('update')
        if (outcome.done) {
          if (this.#canceled) {
            this.status = 'canceled'
            this.notifyLifecycle('update')
            return
          }
          this.#result = outcome.result
          this.status = 'done'
          this.notifyLifecycle('update')
          return
        }
        await delay(this.nextPollDelay(attempt))
        attempt += 1
      }
    } catch (error) {
      this.status = this.#canceled ? 'canceled' : 'error'
      this.reportError(error, { scope: 'BaseAsyncTask.submit' })
      this.notifyLifecycle('update')
    }
  }
}
