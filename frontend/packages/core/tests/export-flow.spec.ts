// kiwi_id: 769
/** 导出流能力基类用例（08-5-1）：契约套件 + 下载触发 + 提示与复位。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseAsyncTask,
  BaseExportFlow,
  BaseFileDownload,
  BaseNotice,
  type ExportResult,
  type ExportScope,
} from '../src'
import {
  describeExportFlowContract,
  type ExportContractJobs,
  type ExportFlowContractTarget,
} from '../testing'

/** 具体导出流（可实例化）。 */
class DemoExportFlow extends BaseExportFlow {}

/** 具体下载触发（可实例化）。 */
class DemoDownload extends BaseFileDownload {}

/** 具体权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 具体提示（可实例化）。 */
class DemoNotice extends BaseNotice {}

/** 契约用异步任务（轮询间隔 1ms，避免测试等待）。 */
class ContractTask extends BaseAsyncTask<ExportResult> {
  constructor() {
    super()
    this.pollInterval = 1
  }
}

/** 契约目标工厂。 */
function makeTarget(): ExportFlowContractTarget {
  const flow = new DemoExportFlow()
  let access: DemoAccess | undefined
  return {
    get ready() {
      return flow.ready
    },
    get degraded() {
      return flow.degraded
    },
    get busy() {
      return flow.busy
    },
    get requestCount() {
      return flow.requestCount
    },
    get phase() {
      return flow.phase
    },
    get progress() {
      return flow.progress
    },
    get canExport() {
      return flow.canExport
    },
    get asyncMode() {
      return flow.asyncMode
    },
    get empty() {
      return flow.empty
    },
    get exportReady() {
      return flow.exportReady
    },
    plan: () => flow.plan,
    setReady: (value) => flow.setReady(value),
    setBiz: (biz, bizName) => flow.setBiz(biz, bizName),
    setParams: (params) => flow.setParams(params),
    setScope: (scope, selectedIds) => flow.setScope(scope as ExportScope, selectedIds),
    setTotal: (total) => flow.setTotal(total),
    setPlain: (plain) => flow.setPlain(plain),
    setThreshold: (threshold) => flow.setThreshold(threshold),
    setDisabled: (disabled) => flow.setDisabled(disabled),
    setAccess: (codes) => {
      if (codes === undefined) {
        flow.access = undefined
        return
      }
      access = new DemoAccess()
      access.setCodes(codes)
      flow.access = access
    },
    setJobs: (jobs: ExportContractJobs) => {
      flow.jobs = jobs
    },
    newTask: () => new ContractTask(),
    setTask: (task) => {
      flow.task = task as BaseAsyncTask<ExportResult> | undefined
    },
    setDownload: (download) => {
      flow.download = download as BaseFileDownload | undefined
    },
    lastResult: () => flow.lastResult,
    export: () => flow.export(),
    retry: () => flow.retry(),
    cancel: () => flow.cancel(),
    reset: () => flow.reset(),
  }
}

describeExportFlowContract('导出流契约（BaseExportFlow 实现）', makeTarget)

describe('导出流能力（提示 / 复位 / 保存载荷）', () => {
  /** 构造已就绪导出流。 */
  const readyFlow = (): DemoExportFlow => {
    const flow = new DemoExportFlow()
    flow.setBiz('users', '用户')
    flow.setTotal(10)
    flow.setParams({ keyword: 'a' })
    flow.setReady(true)
    return flow
  }

  it('同步导出成功：提示入队与结果保留下载信息', async () => {
    const flow = readyFlow()
    const notice = new DemoNotice()
    flow.notice = notice
    flow.jobs = { export: async () => ({ url: 'https://example.test/1.xlsx', fileName: 'users.xlsx' }) }
    await flow.export()
    expect(notice.queue[0]?.type).toBe('success')
    expect(flow.lastResult?.fileName).toBe('users.xlsx')
  })

  it('结果经下载基类触发下载', async () => {
    const flow = readyFlow()
    const download = new DemoDownload()
    const seen: string[] = []
    download.trigger = ({ filename }) => seen.push(filename)
    flow.download = download
    flow.jobs = { export: async () => ({ url: 'https://example.test/1.xlsx', fileName: 'users-2026.xlsx' }) }
    await flow.export()
    expect(seen).toEqual(['users-2026.xlsx'])
    expect(download.phase).toBe('done')
  })

  it('超阈值且轮询注入：经异步任务两段推进进度', async () => {
    const flow = readyFlow()
    flow.setTotal(1000)
    flow.setThreshold(500)
    flow.task = new ContractTask()
    flow.jobs = {
      export: async () => ({ fileId: 'task-1' }),
      poll: async (_handle, attempt) =>
        attempt < 2
          ? { done: false, progress: { value: attempt, total: 2 } }
          : { done: true, progress: { value: 2, total: 2 }, result: { fileId: 'file-1', url: 'https://example.test/1.xlsx' } },
    }
    await expect(flow.export()).resolves.toMatchObject({ fileId: 'file-1' })
    expect(flow.phase).toBe('done')
    expect(flow.progress).toMatchObject({ value: 2, total: 2 })
  })

  it('明文按 data:plain 权限收窄（无权限按脱敏）', () => {
    const flow = readyFlow()
    flow.setPlain(true)
    expect(flow.plan.plain).toBe(false)
    const access = new DemoAccess()
    access.setCodes(['export:download', 'data:plain'])
    flow.access = access
    expect(flow.plan.plain).toBe(true)
    expect(flow.canExport).toBe(true)
  })

  it('复位清阶段、错误、进度与结果', async () => {
    const flow = readyFlow()
    flow.jobs = {
      export: async () => {
        throw new Error('导出失败')
      },
    }
    await flow.export()
    expect(flow.phase).toBe('failed')
    flow.reset()
    expect(flow.phase).toBe('idle')
    expect(flow.errorMessage).toBe('')
    expect(flow.lastResult).toBeUndefined()
    expect(flow.progress).toEqual({ value: 0, total: 0 })
  })
})
