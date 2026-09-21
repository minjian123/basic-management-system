// kiwi_id: 965
/** 文件上传族组件基类用例（06_07）：契约同实现 + 身份依赖 + 预签名预览 / 下载回落。 */

import { describe, expect, it } from 'vitest'

import {
  BaseComponent,
  BaseFileUpload,
  BaseInput,
  BasePresignedUrl,
  BaseUploadEngine,
  type FileAcceptResult,
  type FileKind,
  type FileMeta,
  type FileRef,
  type FileUploadOptions,
  type UploadTaskSnapshot,
  type UploadTransportAdapter,
} from '@bms/core'
import { createUploadTransportStub, describeFileUploadContract, type FileUploadContractTarget } from '@bms/core/testing'

/** 具体文件上传族（可实例化）。 */
class FileUploadState extends BaseFileUpload {}

/** 具体上传引擎（可实例化）。 */
class UploadEngineState extends BaseUploadEngine<unknown> {}

/** 具体预签名（可实例化）。 */
class PresignedState extends BasePresignedUrl {}

/**
 * 把文件族基类适配为契约目标（投影层同构适配；核心侧显式装配内建引擎）。
 *
 * @returns 契约目标。
 */
function makeTarget(): FileUploadContractTarget {
  const upload = new FileUploadState()
  upload.setEngine(new UploadEngineState())
  return {
    get ready() {
      return upload.ready
    },
    get degraded() {
      return upload.degraded
    },
    get requestCount() {
      return upload.requestCount
    },
    get refs(): readonly FileRef[] {
      return upload.refs
    },
    get tasks(): readonly UploadTaskSnapshot[] {
      return upload.tasks
    },
    get empty() {
      return upload.empty
    },
    get limitExceeded() {
      return upload.limitExceeded
    },
    get fileError() {
      return upload.fileError
    },
    get errorCode() {
      return upload.errorCode
    },
    get value(): string | string[] | undefined {
      return upload.value
    },
    setReady: (value) => upload.setReady(value),
    setTransport: (transport) => upload.setTransport(transport),
    setOptions: (options: FileUploadOptions) => upload.setOptions(options),
    setValue: (value) => upload.setValue(value),
    acceptFiles: (inputs: readonly { file: unknown; meta: FileMeta }[]): FileAcceptResult => upload.acceptFiles(inputs),
    remove: (id) => upload.remove(id),
    clearFiles: () => upload.clearFiles(),
    moveFile: (from, to) => upload.moveFile(from, to),
    resolveFiles: (ids) => upload.resolveFiles(ids),
    retryTask: (taskId) => upload.retryTask(taskId),
    cancelTask: (taskId) => upload.cancelTask(taskId),
    labelOf: (id) => upload.labelOf(id),
    summary: () => upload.summary(),
    previewUrlOf: (id) => upload.previewUrlOf(id),
    downloadFile: (id) => upload.downloadFile(id),
  }
}

describeFileUploadContract('文件上传族契约（BaseFileUpload）', makeTarget)

describe('BaseFileUpload 继承链与身份', () => {
  it('身份与依赖登记（入值链）', () => {
    const upload = new FileUploadState()
    expect(upload).toBeInstanceOf(BaseInput)
    expect(upload).toBeInstanceOf(BaseComponent)
    expect(upload.identifier).toBe('file-upload')
    expect(upload.depends).toEqual(['input', 'upload-engine', 'presigned-url', 'file-download'])
    expect(upload.ready).toBe(false)
    expect(upload.kind).toBe<FileKind>('file')
  })

  it('上传完成以服务端标识替换本地占位并同步受控值', async () => {
    const upload = new FileUploadState()
    upload.setEngine(new UploadEngineState())
    const stub = createUploadTransportStub({ dedup: { key: 'f-1' } })
    upload.setOptions({ ready: true, multiple: false, transport: stub.transport })
    const result = upload.acceptFiles([{ file: 'f', meta: { name: 'a.pdf', size: 10, mime: 'application/pdf' } }])
    expect(result.added).toHaveLength(1)
    expect(result.added[0]?.id.startsWith('local:')).toBe(true)
    expect(upload.value).toBeUndefined()
    for (let tick = 0; tick < 50 && upload.value === undefined; tick += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0))
    }
    expect(upload.refs[0]?.id).toBe('f-1')
    expect(upload.value).toBe('f-1')
  })

  it('未就绪时选择不入队并回落占位文案（零请求）', () => {
    const upload = new FileUploadState()
    const stub = createUploadTransportStub()
    upload.setTransport(stub.transport)
    const result = upload.acceptFiles([{ file: 'f', meta: { name: 'a.pdf', size: 10, mime: 'application/pdf' } }])
    expect(result.added).toHaveLength(0)
    expect(upload.refs).toHaveLength(0)
    expect(upload.fileError).toBe('文件上传未就绪（占位）')
    expect(upload.requestCount).toBe(0)
    expect(stub.calls).toEqual([])
  })

  it('预签名预览：按标识取址并缓存（二次零请求）', async () => {
    const upload = new FileUploadState()
    const presigned = new PresignedState()
    let calls = 0
    presigned.fetcher = async (input) => {
      calls += 1
      return { url: `https://signed/${input?.key ?? ''}`, expiresAt: Date.now() + 3_600_000 }
    }
    upload.setPresigned(presigned)
    upload.setValue('f1')
    expect(await upload.previewUrlOf('f1')).toBe('https://signed/f1')
    expect(await upload.previewUrlOf('f1')).toBe('https://signed/f1')
    expect(calls).toBe(1)
  })

  it('下载回落：未注入下载触发时不动作', async () => {
    const upload = new FileUploadState()
    upload.setValue('f1')
    expect(await upload.downloadFile('f1')).toBeUndefined()
  })

  it('校验拒绝不改变引用并置错误码', () => {
    const upload = new FileUploadState()
    upload.setOptions({ ready: true, accept: '.pdf', maxSize: 1024 })
    upload.setTransport({} as UploadTransportAdapter)
    const result = upload.acceptFiles([{ file: 'f', meta: { name: 'a.png', size: 10, mime: 'image/png' } }])
    expect(result.rejected[0]?.code).toBe(50101)
    expect(upload.fileError).not.toBe('')
    expect(upload.refs).toHaveLength(0)
  })
})
