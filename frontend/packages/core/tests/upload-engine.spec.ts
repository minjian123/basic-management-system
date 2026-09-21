// kiwi_id: 965
/** 上传引擎能力基类用例（06_07）：契约同实现 + 身份依赖 + 既有单文件路径回归。 */

import { describe, expect, it } from 'vitest'

import { BaseComponent, BasePlaceholderState, BaseUploadEngine } from '@bms/core'
import { createUploadTransportStub, describeUploadEngineContract, type UploadEngineContractTarget } from '@bms/core/testing'

/** 具体上传引擎（可实例化）。 */
class UploadEngineState extends BaseUploadEngine<unknown> {}

/**
 * 把引擎基类适配为契约目标（投影层同构适配）。
 *
 * @returns 契约目标。
 */
function makeTarget(): UploadEngineContractTarget {
  const engine = new UploadEngineState()
  return {
    get ready() {
      return engine.ready
    },
    get degraded() {
      return engine.degraded
    },
    get requestCount() {
      return engine.requestCount
    },
    get tasks() {
      return engine.tasks
    },
    get busy() {
      return engine.busy
    },
    get totalPercent() {
      return engine.totalPercent
    },
    get doneCount() {
      return engine.doneCount
    },
    get failedCount() {
      return engine.failedCount
    },
    get canUpload() {
      return engine.canUpload
    },
    setReady: (value) => engine.setReady(value),
    setTransport: (transport) => engine.setTransport(transport),
    setConfig: (input) => engine.setConfig(input),
    enqueue: (input) => engine.enqueue(input),
    start: (taskId) => engine.start(taskId),
    retry: (taskId) => engine.retry(taskId),
    cancel: (taskId) => engine.cancel(taskId),
    remove: (taskId) => engine.remove(taskId),
    taskOf: (taskId) => engine.taskOf(taskId),
    reset: () => engine.reset(),
  }
}

describeUploadEngineContract('上传引擎契约（BaseUploadEngine）', makeTarget)

describe('BaseUploadEngine 继承链与身份', () => {
  it('身份与依赖登记（重挂占位语义）', () => {
    const engine = new UploadEngineState()
    expect(engine).toBeInstanceOf(BasePlaceholderState)
    expect(engine).toBeInstanceOf(BaseComponent)
    expect(engine.identifier).toBe('upload-engine')
    expect(engine.depends).toEqual(['placeholder-state', 'presigned-url'])
    expect(engine.ready).toBe(false)
  })

  it('重试复用会话与已传分片（断点续传）', async () => {
    const engine = new UploadEngineState()
    const stub = createUploadTransportStub({ partSize: 1024 * 1024 })
    stub.failPartOnce.add(2)
    engine.setReady(true)
    engine.setTransport(stub.transport)
    engine.setConfig({ wholeMaxSize: 1024 * 1024, partSize: 1024 * 1024, retryMax: 0 })
    const taskId = engine.enqueue({ file: 'f', meta: { name: 'd.bin', size: 2 * 1024 * 1024 + 100, mime: 'application/octet-stream' } })
    await engine.start(taskId)
    expect(engine.taskOf(taskId as string)?.phase).toBe('failed')
    stub.failPartOnce.clear()
    await engine.retry(taskId as string)
    expect(engine.taskOf(taskId as string)?.phase).toBe('done')
    expect(stub.calls.filter((call) => call === 'initiate')).toHaveLength(1)
    expect(stub.uploadedParts.sort()).toEqual([1, 2, 3])
  })

  it('取消不视为失败且进度复位；未就绪入队零请求', async () => {
    const engine = new UploadEngineState()
    const stub = createUploadTransportStub()
    expect(engine.enqueue({ file: 'f', meta: { name: 'a.pdf', size: 10, mime: 'application/pdf' } })).toBeUndefined()
    expect(engine.errorMessage).toBe('文件上传未就绪（占位）')
    engine.setReady(true)
    engine.setTransport(stub.transport)
    const taskId = engine.enqueue({ file: 'f', meta: { name: 'a.pdf', size: 10, mime: 'application/pdf' } })
    engine.cancel(taskId as string)
    expect(engine.taskOf(taskId as string)?.phase).toBe('canceled')
    expect(engine.taskOf(taskId as string)?.percent).toBe(0)
    expect(engine.failedCount).toBe(0)
  })
})
