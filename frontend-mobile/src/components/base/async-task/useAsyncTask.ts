/**
 * 异步任务片段（`async-task`）：长时任务的提交、进度轮询、取消与结果下载。
 *
 * 契约见《组件设计 · 异步任务片段》：`submit` / `poll`（指数退避）/ `cancel` / `download` +
 * 进度与状态（导入导出、报表与大屏导出共用）。**占位先行**：未注入 `submitter`（任务调度未接入）
 * 时提交即进入 `placeholder` 态（**不发请求**），消费方据此隐藏进度或提示「暂不可用」。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 任务状态 */
export type AsyncTaskStatus = 'idle' | 'submitted' | 'running' | 'completed' | 'failed' | 'cancelled' | 'placeholder'

/** 轮询结果（后端任务进度接口口径） */
export interface TaskPollResult {
  status: 'running' | 'completed' | 'failed'
  progress?: number
  message?: string
}

/** 异步任务片段参数 */
export interface UseAsyncTaskOptions {
  /** 任务类型（后端任务调度按类型派发，如 `export` / `import` / `report`） */
  taskType?: MaybeRefOrGetter<string>
  /** 轮询起始间隔（毫秒，默认 1000） */
  pollInterval?: MaybeRefOrGetter<number>
  /** 轮询最大间隔（退避上限，默认 10000） */
  pollMaxInterval?: MaybeRefOrGetter<number>
  /** 失败重试次数（默认 1） */
  retry?: MaybeRefOrGetter<number>
  /** 状态变化通知（供界面提示） */
  notify?: (status: AsyncTaskStatus, message?: string) => void
  /** 提交器（缺省即占位） */
  submitter?: (payload: unknown) => Promise<{ taskId: string }>
  /** 轮询器（缺省即占位） */
  poller?: (taskId: string) => Promise<TaskPollResult>
  /** 结果下载器（缺省即占位） */
  downloader?: (taskId: string) => Promise<string>
}

/** 异步任务片段返回值 */
export interface UseAsyncTaskReturn {
  readonly status: AsyncTaskStatus
  readonly taskId: string | undefined
  readonly progress: number
  readonly message: string
  readonly isRunning: boolean
  /** 占位态：任务调度未接入 */
  readonly isPlaceholder: boolean
  submit: (payload?: unknown) => Promise<string>
  poll: (taskId: string) => Promise<AsyncTaskStatus>
  cancel: () => void
  download: (taskId?: string) => Promise<string>
  reset: () => void
}

/** 可中断的延时（ms） */
function delay(ms: number, isCancelled: () => boolean): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms)
    if (isCancelled()) {
      clearTimeout(timer)
      resolve()
    }
  })
}

/**
 * 获取异步任务能力。
 *
 * 用法：`const task = useAsyncTask({ taskType: 'export', submitter, poller, downloader })`；
 * 后端任务调度未就绪时省略三者即得占位行为。
 */
export function useAsyncTask(options: UseAsyncTaskOptions = {}): UseAsyncTaskReturn {
  const capability = declareFragment('async-task')

  const status = ref<AsyncTaskStatus>('idle')
  const taskId = ref<string | undefined>(undefined)
  const progress = ref(0)
  const message = ref('')
  const cancelled = ref(false)

  const isPlaceholder = computed(() => options.submitter === undefined || options.poller === undefined)

  const setStatus = (next: AsyncTaskStatus, note?: string): void => {
    status.value = next
    message.value = note ?? ''
    options.notify?.(next, note)
  }

  const submit = async (payload?: unknown): Promise<string> => {
    cancelled.value = false
    progress.value = 0
    if (isPlaceholder.value || !options.submitter) {
      const placeholderId = `placeholder-${Date.now()}`
      taskId.value = placeholderId
      setStatus('placeholder', '任务调度未接入（占位）')
      capability.log('debug', 'async-task 占位：提交器未接入，不发请求')
      return placeholderId
    }
    setStatus('submitted')
    const result = await options.submitter(payload)
    taskId.value = result.taskId
    setStatus('running')
    return result.taskId
  }

  const poll = async (id: string): Promise<AsyncTaskStatus> => {
    if (isPlaceholder.value || !options.poller) {
      setStatus('placeholder', '任务进度未接入（占位）')
      return 'placeholder'
    }
    const start = Number(toValue(options.pollInterval) ?? 1000)
    const max = Number(toValue(options.pollMaxInterval) ?? 10000)
    const retryLimit = Number(toValue(options.retry) ?? 1)
    let wait = start
    let failures = 0
    while (!cancelled.value) {
      try {
        const result = await options.poller(id)
        failures = 0
        progress.value = result.progress ?? progress.value
        if (result.status === 'completed') {
          progress.value = 100
          setStatus('completed', result.message)
          return 'completed'
        }
        if (result.status === 'failed') {
          setStatus('failed', result.message)
          return 'failed'
        }
      } catch (error) {
        failures += 1
        capability.reportError(error, { scope: 'async-task.poll', taskType: toValue(options.taskType) })
        if (failures > retryLimit) {
          setStatus('failed', '进度查询失败')
          return 'failed'
        }
      }
      await delay(wait, () => cancelled.value)
      wait = Math.min(wait * 2, max)
    }
    setStatus('cancelled')
    return 'cancelled'
  }

  const cancel = (): void => {
    cancelled.value = true
    setStatus('cancelled')
  }

  const download = async (id?: string): Promise<string> => {
    const target = id ?? taskId.value
    if (!target || !options.downloader) {
      capability.log('debug', 'async-task 占位：下载器未接入')
      return ''
    }
    return options.downloader(target)
  }

  return {
    get status() {
      return status.value
    },
    get taskId() {
      return taskId.value
    },
    get progress() {
      return progress.value
    },
    get message() {
      return message.value
    },
    get isRunning() {
      return status.value === 'submitted' || status.value === 'running'
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    submit,
    poll,
    cancel,
    download,
    reset: () => {
      cancelled.value = false
      taskId.value = undefined
      progress.value = 0
      setStatus('idle')
    },
  }
}
