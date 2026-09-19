// kiwi_id: 769
/** 导入流能力基类用例（08-5-1）：契约套件 + 上传引擎路径 + 下载通路 + 权限与提示。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseFileDownload,
  BaseImportFlow,
  BaseNotice,
  BasePresignedUrl,
  BaseUploadEngine,
  IMPORT_PLACEHOLDER_TEXT,
  type ImportFileMeta,
} from '../src'
import {
  describeImportFlowContract,
  type ImportContractJobs,
  type ImportFlowContractTarget,
} from '../testing'

/** 具体导入流（可实例化）。 */
class DemoImportFlow extends BaseImportFlow {}

/** 具体上传引擎（可实例化）。 */
class DemoEngine extends BaseUploadEngine<unknown> {}

/** 具体下载触发（可实例化）。 */
class DemoDownload extends BaseFileDownload {}

/** 具体预签名（可实例化）。 */
class DemoPresigned extends BasePresignedUrl {}

/** 具体权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 具体提示（可实例化）。 */
class DemoNotice extends BaseNotice {}

/** 契约目标工厂。 */
function makeTarget(): ImportFlowContractTarget {
  const flow = new DemoImportFlow()
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
    get step() {
      return flow.step
    },
    get progress() {
      return flow.progress
    },
    get idempotencyKey() {
      return flow.idempotencyKey
    },
    get fileError() {
      return flow.fileError
    },
    get summary() {
      return flow.summary
    },
    get errorPageCount() {
      return flow.errorPageCount
    },
    get errorRows() {
      return flow.errorRows
    },
    get errorTruncated() {
      return flow.errorTruncated
    },
    setReady: (value) => flow.setReady(value),
    setBiz: (biz, bizName) => flow.setBiz(biz, bizName),
    setJobs: (jobs: ImportContractJobs) => {
      flow.jobs = jobs
    },
    setDownload: (download) => {
      flow.download = download as BaseFileDownload | undefined
    },
    selectFile: (file, meta: ImportFileMeta) => flow.selectFile(file, meta),
    clearFile: () => flow.clearFile(),
    setErrorPage: (page) => flow.setErrorPage(page),
    submit: () => flow.submit(),
    retry: () => flow.retry(),
    reset: () => flow.reset(),
    cancel: () => flow.cancel(),
    downloadTemplate: () => flow.downloadTemplate(),
    downloadErrors: () => flow.downloadErrors(),
    result: () => flow.result,
  }
}

describeImportFlowContract('导入流契约（BaseImportFlow 实现）', makeTarget)

describe('导入流能力（引擎 / 下载 / 权限 / 提示）', () => {
  /** 构造已就绪且已选文件的导入流。 */
  const readyFlow = (): DemoImportFlow => {
    const flow = new DemoImportFlow()
    flow.setBiz('users', '用户')
    flow.setReady(true)
    flow.selectFile({ name: 'users.xlsx' }, { name: 'users.xlsx', size: 1024 })
    return flow
  }

  it('注入上传引擎时进度经引擎透出，取消中断在途请求', async () => {
    const flow = readyFlow()
    const engine = new DemoEngine()
    flow.engine = engine
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    flow.jobs = {
      execute: async ({ report }) => {
        report(40)
        await gate
        return { total: 1, successCount: 1, failCount: 0 }
      },
    }

    const pending = flow.submit()
    await expect(flow.submit()).resolves.toBeUndefined()
    expect(engine.progress).toBe(40)
    flow.cancel()
    expect(engine.canceled).toBe(true)
    release()
    await expect(pending).resolves.toBeUndefined()
    expect(flow.phase).toBe('idle')
    expect(flow.progress).toBe(0)
  })

  it('注入上传引擎且执行成功：引擎进度置满', async () => {
    const flow = readyFlow()
    const engine = new DemoEngine()
    flow.engine = engine
    flow.jobs = { execute: async () => ({ total: 1, successCount: 1, failCount: 0 }) }
    await expect(flow.submit()).resolves.toEqual({ total: 1, successCount: 1, failCount: 0, errors: [] })
    expect(engine.progress).toBe(100)
    expect(flow.phase).toBe('done')
  })

  it('注入下载基类：模板与错误明细经其触发', async () => {
    const flow = readyFlow()
    const download = new DemoDownload()
    const seen: string[] = []
    download.trigger = ({ filename }) => seen.push(filename)
    flow.download = download
    flow.jobs = { downloadTemplate: async () => ({ url: 'https://example.test/t.xlsx' }) }

    await expect(flow.downloadTemplate()).resolves.toEqual({
      url: 'https://example.test/t.xlsx',
      filename: '用户-导入模板.xlsx',
    })
    expect(seen).toEqual(['用户-导入模板.xlsx'])
    expect(download.phase).toBe('done')
  })

  it('权限上下文缺 import:execute 时不可提交且零请求', async () => {
    const flow = readyFlow()
    const access = new DemoAccess()
    flow.access = access
    flow.jobs = { execute: async () => ({ total: 1 }) }

    expect(flow.canImport).toBe(false)
    await expect(flow.submit()).resolves.toBeUndefined()
    expect(flow.requestCount).toBe(0)

    access.setCodes(['import:execute'])
    expect(flow.canImport).toBe(true)
    await expect(flow.submit()).resolves.toBeDefined()
  })

  it('提示通知：成功与失败按结果类型入队', async () => {
    const flow = readyFlow()
    const notice = new DemoNotice()
    flow.notice = notice
    flow.jobs = { execute: async () => ({ total: 2, successCount: 1, failCount: 1, errors: [{ row: 2, message: '非法' }] }) }
    await flow.submit()
    expect(notice.queue[0]?.type).toBe('warning')
    expect(notice.queue[0]?.content).toContain('成功 1 行')

    flow.reset()
    flow.selectFile({ name: 'users.xlsx' }, { name: 'users.xlsx', size: 1024 })
    flow.jobs = {
      execute: async () => {
        throw new Error('解析失败')
      },
    }
    await flow.submit()
    expect(flow.phase).toBe('failed')
    expect(flow.errorMessage).toBe('解析失败')
    expect(notice.queue.at(-1)?.type).toBe('error')
  })

  it('占位文案：未注入执行处理时写入占位提示且不请求', async () => {
    const flow = readyFlow()
    await flow.submit()
    expect(flow.errorMessage).toBe(IMPORT_PLACEHOLDER_TEXT)
    expect(flow.requestCount).toBe(0)
  })

  it('预签名能力可作为下载取址回退（经下载基类）', async () => {
    const flow = readyFlow()
    const download = new DemoDownload()
    const presigned = new DemoPresigned()
    presigned.url = 'https://example.test/errors.xlsx'
    presigned.expiresAt = Date.now() + 60_000
    download.presigned = presigned
    const seen: string[] = []
    download.trigger = ({ url }) => seen.push(url ?? '')
    flow.download = download

    await flow.downloadErrors()
    expect(seen).toEqual(['https://example.test/errors.xlsx'])
  })
})
