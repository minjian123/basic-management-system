/** 异步任务能力：提交 / 轮询进度（退避由注入 poller 承担）/ 取消（占位先行）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export type TaskState = 'idle' | 'running' | 'done' | 'error' | 'canceled'

export interface AsyncTaskOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  submit?: () => Promise<string>
  poll?: (taskId: string) => Promise<{ state: TaskState; percent?: number }>
}

export class BaseAsyncTask extends BaseCapability {
  readonly state = observable<TaskState>('idle')
  readonly percent = observable(0)
  readonly taskId = observable('')
  private canceled = false
  private readonly options: AsyncTaskOptions

  constructor(options: AsyncTaskOptions = {}) {
    super({ ...options, key: options.key ?? 'async-task' })
    this.options = options
  }

  async run(): Promise<TaskState> {
    this.canceled = false
    if (!this.options.submit || !this.options.poll) {
      this.state.set('done') // 占位：不发请求
      return 'done'
    }
    this.state.set('running')
    try {
      const taskId = await this.options.submit()
      this.taskId.set(taskId)
      for (;;) {
        if (this.canceled) {
          this.state.set('canceled')
          return 'canceled'
        }
        const status = await this.options.poll(taskId)
        this.percent.set(status.percent ?? this.percent.get())
        if (status.state !== 'running') {
          this.state.set(status.state)
          return status.state
        }
      }
    } catch (error) {
      this.state.set('error')
      this.reportError(error, { phase: 'async-task' })
      return 'error'
    }
  }

  cancel(): void {
    this.canceled = true
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), state: this.state.get(), placeholder: !this.options.submit }
  }
}
