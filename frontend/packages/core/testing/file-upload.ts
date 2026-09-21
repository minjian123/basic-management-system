/**
 * 文件契约（`@bms/core/testing`）。
 *
 * 上传引擎 / 文件上传族为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、秒传、整包与分片决策、并发、失败重试、断点续传、取消、校验与上限、
 * 受控值同步、批量回显与失效、排序与移除、图片校验与预览下载回落。
 */

import { describe, expect, it } from 'vitest'

import type {
  FileAcceptResult,
  FileMeta,
  FileRef,
  FileUploadOptions,
  UploadTaskSnapshot,
  UploadTransportAdapter,
} from '../src'

/** 契约文件：普通文件。 */
export const FILE_CONTRACT_PDF: FileMeta = { name: 'a.pdf', size: 1024, mime: 'application/pdf' }
/** 契约文件：图片。 */
export const FILE_CONTRACT_IMAGE: FileMeta = { name: 'b.png', size: 2 * 1024 * 1024, mime: 'image/png' }
/** 契约文件：空文件。 */
export const FILE_CONTRACT_EMPTY: FileMeta = { name: 'c.txt', size: 0, mime: 'text/plain' }
/** 契约文件：大文件（触发分片）。 */
export const FILE_CONTRACT_LARGE: FileMeta = { name: 'd.bin', size: 2 * 1024 * 1024 + 100, mime: 'application/octet-stream' }

/** 上传通路桩（记录调用轨迹与查询入参；可控失败 / 慢分片 / 秒传命中）。 */
export interface UploadTransportStub {
  /** 通路实现。 */
  transport: UploadTransportAdapter
  /** 调用轨迹。 */
  calls: string[]
  /** 查询入参轨迹。 */
  queries: Record<string, unknown>[]
  /** 已传分片。 */
  uploadedParts: number[]
  /** 已取消会话。 */
  aborted: string[]
  /** 首次失败的分片序号（消费后移除）。 */
  failPartOnce: Set<number>
  /** 释放慢分片（`slowPart` 开启时）。 */
  release(): void
}

/**
 * 创建上传通路桩。
 *
 * @param options 选项（分片大小 / 秒传命中 / 已传分片 / 慢分片 / 覆写方法）。
 * @returns 通路桩。
 */
export function createUploadTransportStub(options: {
  partSize?: number
  dedup?: Record<string, unknown> | null
  wholeKey?: string
  storedKey?: string
  uploadedParts?: readonly number[]
  withListParts?: boolean
  slowPart?: boolean
  overrides?: UploadTransportAdapter
} = {}): UploadTransportStub {
  const calls: string[] = []
  const queries: Record<string, unknown>[] = []
  const uploadedParts: number[] = []
  const aborted: string[] = []
  const failPartOnce = new Set<number>()
  const releases: (() => void)[] = []
  const partSize = options.partSize ?? 1024 * 1024
  const stub: UploadTransportStub = {
    calls,
    queries,
    uploadedParts,
    aborted,
    failPartOnce,
    release: () => {
      while (releases.length > 0) {
        const release = releases.shift()
        release?.()
      }
    },
    transport: {
      hash: async (query) => {
        calls.push('hash')
        queries.push({ partSize: query.partSize })
        return { sha256: 'a'.repeat(64) }
      },
      check: async (query) => {
        calls.push('check')
        queries.push({ sha256: query.sha256, size: query.size })
        return options.dedup ?? null
      },
      uploadWhole: async (query) => {
        calls.push('uploadWhole')
        queries.push({ name: query.name, size: query.size })
        query.report?.(100)
        return { key: options.wholeKey ?? 'whole-1', size: query.size, content_type: query.mime }
      },
      initiate: async (query) => {
        calls.push('initiate')
        queries.push({ size: query.size, partSize: query.partSize })
        return {
          upload_id: 'u1',
          key: 'k1',
          part_size: partSize,
          total_parts: Math.ceil(query.size / partSize),
        }
      },
      uploadPart: async (query) => {
        calls.push('uploadPart')
        queries.push({ partNo: query.partNo, start: query.start, end: query.end })
        if (options.slowPart === true) {
          await new Promise<void>((resolve) => {
            releases.push(resolve)
          })
        }
        if (failPartOnce.has(query.partNo)) {
          failPartOnce.delete(query.partNo)
          throw Object.assign(new Error('分片失败'), { code: 50104 })
        }
        uploadedParts.push(query.partNo)
        return { part_no: query.partNo, etag: `etag-${query.partNo}`, size: query.end - query.start }
      },
      complete: async (query) => {
        calls.push('complete')
        queries.push({ uploadId: query.uploadId })
        return { key: options.storedKey ?? 'stored-1', size: 0, content_type: 'application/octet-stream' }
      },
      abort: async (query) => {
        calls.push('abort')
        aborted.push(query.uploadId)
      },
      ...(options.withListParts === true
        ? {
            listParts: async (query: { uploadId: string }) => {
              calls.push('listParts')
              queries.push({ uploadId: query.uploadId })
              return options.uploadedParts ?? []
            },
          }
        : {}),
      resolveFiles: async (query) => {
        calls.push('resolveFiles')
        queries.push({ ids: [...query.ids] })
        return [{ id: 'f1', name: '已回显.pdf', size: 2048, mime: 'application/pdf' }]
      },
      presign: async (query) => {
        calls.push('presign')
        queries.push({ fileId: query.fileId, purpose: query.purpose })
        return { url: `https://signed/${query.fileId}`, expires_in: 3600 }
      },
      ...options.overrides,
    },
  }
  return stub
}

/** 上传引擎契约目标（结构化接口）。 */
export interface UploadEngineContractTarget {
  /** 是否就绪。 */
  readonly ready: boolean
  /** 是否降级。 */
  readonly degraded: boolean
  /** 请求计数。 */
  readonly requestCount: number
  /** 任务快照。 */
  readonly tasks: readonly UploadTaskSnapshot[]
  /** 是否在途。 */
  readonly busy: boolean
  /** 聚合进度。 */
  readonly totalPercent: number
  /** 完成数。 */
  readonly doneCount: number
  /** 失败数。 */
  readonly failedCount: number
  /** 是否可上传。 */
  readonly canUpload: boolean
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除通路。 */
  setTransport(transport: UploadTransportAdapter | undefined): void
  /** 配置。 */
  setConfig(input: { wholeMaxSize?: number; partSize?: number; concurrency?: number; retryMax?: number; autoDedup?: boolean }): void
  /** 入队。 */
  enqueue(input: { file: unknown; meta: FileMeta; key?: string }): string | undefined
  /** 启动。 */
  start(taskId?: string): Promise<void>
  /** 重试。 */
  retry(taskId: string): Promise<void>
  /** 取消。 */
  cancel(taskId?: string): void
  /** 移除。 */
  remove(taskId: string): void
  /** 取任务。 */
  taskOf(taskId: string): UploadTaskSnapshot | undefined
  /** 重置。 */
  reset(): void
}

/** 文件上传族契约目标（结构化接口）。 */
export interface FileUploadContractTarget {
  /** 是否就绪。 */
  readonly ready: boolean
  /** 是否降级。 */
  readonly degraded: boolean
  /** 请求计数。 */
  readonly requestCount: number
  /** 引用列表。 */
  readonly refs: readonly FileRef[]
  /** 任务快照。 */
  readonly tasks: readonly UploadTaskSnapshot[]
  /** 是否空态。 */
  readonly empty: boolean
  /** 多选超限标记。 */
  readonly limitExceeded: boolean
  /** 校验 / 上传失败文案。 */
  readonly fileError: string
  /** 错误码。 */
  readonly errorCode: number | undefined
  /** 受控值。 */
  readonly value: string | string[] | undefined
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除通路。 */
  setTransport(transport: UploadTransportAdapter | undefined): void
  /** 装配选项。 */
  setOptions(options: FileUploadOptions): void
  /** 设置受控值。 */
  setValue(value: string | string[] | undefined): void
  /** 接受文件。 */
  acceptFiles(inputs: readonly { file: unknown; meta: FileMeta }[]): FileAcceptResult
  /** 移除。 */
  remove(id: string): void
  /** 清空。 */
  clearFiles(): void
  /** 排序。 */
  moveFile(from: number, to: number): void
  /** 批量回显。 */
  resolveFiles(ids?: readonly string[]): Promise<void>
  /** 重试任务。 */
  retryTask(taskId: string): Promise<void>
  /** 取消任务。 */
  cancelTask(taskId: string): void
  /** 展示文案。 */
  labelOf(id: string): string
  /** 摘要。 */
  summary(): string
  /** 预览地址。 */
  previewUrlOf(id: string): Promise<string | undefined>
  /** 下载。 */
  downloadFile(id: string): Promise<unknown>
}

/**
 * 上传引擎契约（同契约多实现）。
 *
 * @param name 契约名。
 * @param create 目标工厂（每次返回全新实例）。
 */
export function describeUploadEngineContract(name: string, create: () => UploadEngineContractTarget): void {
  describe(name, () => {
    it('占位零请求：未就绪 / 未注入通路不入队、不请求', async () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setTransport(stub.transport)
      expect(target.enqueue({ file: 'f', meta: FILE_CONTRACT_PDF })).toBeUndefined()
      await target.start()
      expect(target.requestCount).toBe(0)
      expect(stub.calls).toEqual([])
      expect(target.tasks).toHaveLength(0)

      target.setReady(true)
      target.setTransport(undefined)
      expect(target.enqueue({ file: 'f', meta: FILE_CONTRACT_PDF })).toBeUndefined()
      await target.start()
      expect(target.requestCount).toBe(0)
    })

    it('秒传命中：零上传直接完成', async () => {
      const target = create()
      const stub = createUploadTransportStub({ dedup: { key: 'dedup-1', size: 1024, content_type: 'application/pdf' } })
      target.setReady(true)
      target.setTransport(stub.transport)
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_PDF })
      expect(taskId).toBeDefined()
      await target.start(taskId)
      const task = target.taskOf(taskId as string)
      expect(task?.phase).toBe('done')
      expect(task?.fileId).toBe('dedup-1')
      expect(stub.calls).toContain('check')
      expect(stub.calls).not.toContain('uploadWhole')
      expect(stub.calls).not.toContain('uploadPart')
      expect(target.doneCount).toBe(1)
      expect(target.totalPercent).toBe(100)
    })

    it('整包决策：未超阈值走整包', async () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setConfig({ wholeMaxSize: 1024 * 1024, partSize: 1024 * 1024 })
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_PDF })
      await target.start(taskId)
      expect(target.taskOf(taskId as string)?.mode).toBe('whole')
      expect(stub.calls).toContain('uploadWhole')
      expect(stub.calls).not.toContain('uploadPart')
      expect(target.taskOf(taskId as string)?.fileId).toBe('whole-1')
    })

    it('分片决策：超阈值分片上传并按并发完成', async () => {
      const target = create()
      const stub = createUploadTransportStub({ partSize: 1024 * 1024 })
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setConfig({ wholeMaxSize: 1024 * 1024, partSize: 1024 * 1024, concurrency: 2 })
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_LARGE })
      await target.start(taskId)
      expect(target.taskOf(taskId as string)?.mode).toBe('multipart')
      expect(stub.uploadedParts.sort()).toEqual([1, 2, 3])
      expect(stub.calls.filter((call) => call === 'uploadPart')).toHaveLength(3)
      expect(stub.calls).toContain('complete')
      expect(target.taskOf(taskId as string)?.percent).toBe(100)
    })

    it('断点续传：覆写 listParts 时仅补缺失分片', async () => {
      const target = create()
      const stub = createUploadTransportStub({ partSize: 1024 * 1024, withListParts: true, uploadedParts: [1] })
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setConfig({ wholeMaxSize: 1024 * 1024, partSize: 1024 * 1024 })
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_LARGE })
      await target.start(taskId)
      expect(stub.calls).toContain('listParts')
      expect(stub.calls.filter((call) => call === 'uploadPart')).toHaveLength(2)
      expect(stub.uploadedParts.sort()).toEqual([2, 3])
    })

    it('失败重试：分片失败按退避重试一次后成功', async () => {
      const target = create()
      const stub = createUploadTransportStub({ partSize: 1024 * 1024 })
      stub.failPartOnce.add(2)
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setConfig({ wholeMaxSize: 1024 * 1024, partSize: 1024 * 1024, retryMax: 1 })
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_LARGE })
      await target.start(taskId)
      const task = target.taskOf(taskId as string)
      expect(task?.phase).toBe('done')
      expect(task?.attempts).toBeGreaterThanOrEqual(4)
      expect(stub.uploadedParts.sort()).toEqual([1, 2, 3])
    })

    it('失败终态：重试耗尽置失败与错误码', async () => {
      const target = create()
      const stub = createUploadTransportStub({
        partSize: 1024 * 1024,
        overrides: {
          uploadPart: async () => {
            throw Object.assign(new Error('分片失败'), { code: 50104 })
          },
        },
      })
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setConfig({ wholeMaxSize: 1024 * 1024, partSize: 1024 * 1024, retryMax: 0 })
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_LARGE })
      await target.start(taskId)
      const task = target.taskOf(taskId as string)
      expect(task?.phase).toBe('failed')
      expect(task?.errorCode).toBe(50104)
      expect(target.failedCount).toBe(1)
    })

    it('未覆写方法：整包与分片皆无时任务失败且不请求上传', async () => {
      const target = create()
      const calls: string[] = []
      target.setReady(true)
      target.setTransport({
        hash: async () => {
          calls.push('hash')
          return { sha256: 'b'.repeat(64) }
        },
        check: async () => {
          calls.push('check')
          return null
        },
      })
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_PDF })
      await target.start(taskId)
      expect(target.taskOf(taskId as string)?.phase).toBe('failed')
      expect(calls).toEqual(['hash', 'check'])
    })

    it('取消：中断在途任务、进度复位且不视为失败', async () => {
      const target = create()
      const stub = createUploadTransportStub({ partSize: 1024 * 1024, slowPart: true })
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setConfig({ wholeMaxSize: 1024 * 1024, partSize: 1024 * 1024 })
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_LARGE })
      const pending = target.start(taskId)
      for (let tick = 0; tick < 50 && !stub.calls.includes('uploadPart'); tick += 1) {
        await new Promise((resolve) => setTimeout(resolve, 0))
      }
      expect(stub.calls).toContain('uploadPart')
      target.cancel(taskId)
      stub.release()
      await pending
      const task = target.taskOf(taskId as string)
      expect(task?.phase).toBe('canceled')
      expect(task?.percent).toBe(0)
      expect(stub.calls).toContain('abort')
      expect(target.failedCount).toBe(0)
    })

    it('移除与重置：任务表可清空且可重新入队', async () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setReady(true)
      target.setTransport(stub.transport)
      const taskId = target.enqueue({ file: 'f', meta: FILE_CONTRACT_PDF })
      expect(target.tasks).toHaveLength(1)
      target.remove(taskId as string)
      expect(target.tasks).toHaveLength(0)
      expect(target.taskOf(taskId as string)).toBeUndefined()
      target.enqueue({ file: 'f', meta: FILE_CONTRACT_PDF })
      target.reset()
      expect(target.tasks).toHaveLength(0)
      expect(target.busy).toBe(false)
    })
  })
}

/**
 * 文件上传族契约（同契约多实现）。
 *
 * @param name 契约名。
 * @param create 目标工厂（每次返回全新实例）。
 */
export function describeFileUploadContract(name: string, create: () => FileUploadContractTarget): void {
  describe(name, () => {
    it('占位零请求：未就绪 / 未注入通路时校验与回显皆不发请求', async () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setTransport(stub.transport)
      const result = target.acceptFiles([{ file: 'f', meta: FILE_CONTRACT_PDF }])
      expect(result.added).toHaveLength(0)
      await target.resolveFiles(['f1'])
      expect(target.requestCount).toBe(0)
      expect(stub.calls).toEqual([])
      expect(target.degraded).toBe(true)
    })

    it('校验：空文件 / 类型 / 大小被拒且不发请求', () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setOptions({ accept: '.pdf', maxSize: 1024 })

      const empty = target.acceptFiles([{ file: 'f', meta: FILE_CONTRACT_EMPTY }])
      expect(empty.rejected[0]?.code).toBe(50102)
      const type = target.acceptFiles([{ file: 'f', meta: FILE_CONTRACT_IMAGE }])
      expect(type.rejected[0]?.code).toBe(50101)
      const size = target.acceptFiles([{ file: 'f', meta: { name: 'big.pdf', size: 2048, mime: 'application/pdf' } }])
      expect(size.rejected[0]?.code).toBe(50102)
      expect(stub.calls).toEqual([])
      expect(target.refs).toHaveLength(0)
    })

    it('数量上限：超出截断并置超限标记', () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setOptions({ multiple: true, limit: 1 })
      const result = target.acceptFiles([
        { file: 'f1', meta: FILE_CONTRACT_PDF },
        { file: 'f2', meta: { name: 'b.pdf', size: 2048, mime: 'application/pdf' } },
      ])
      expect(result.added).toHaveLength(1)
      expect(result.rejected[0]?.code).toBe(50103)
      expect(target.limitExceeded).toBe(true)
      expect(target.refs).toHaveLength(1)
    })

    it('受控值同步：外部设值与移除 / 清空', () => {
      const target = create()
      target.setOptions({ multiple: true })
      target.setValue(['f1', 'f2'])
      expect(target.refs.map((ref) => ref.id)).toEqual(['f1', 'f2'])
      target.remove('f1')
      expect(target.value).toEqual(['f2'])
      target.clearFiles()
      expect(target.value).toBeUndefined()
      expect(target.refs).toHaveLength(0)
      expect(target.empty).toBe(true)
    })

    it('排序：多图移动同步受控值顺序', () => {
      const target = create()
      target.setOptions({ multiple: true })
      target.setValue(['f1', 'f2', 'f3'])
      target.moveFile(0, 2)
      expect(target.value).toEqual(['f2', 'f3', 'f1'])
    })

    it('批量回显：一次批量、二次零请求、未命中失效', async () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setValue(['f1', 'f9'])
      await target.resolveFiles()
      expect(stub.calls.filter((call) => call === 'resolveFiles')).toHaveLength(1)
      const f1 = target.refs.find((ref) => ref.id === 'f1')
      expect(f1?.name).toBe('已回显.pdf')
      expect(target.labelOf('f9')).toContain('文件已失效')
      await target.resolveFiles()
      expect(stub.calls.filter((call) => call === 'resolveFiles')).toHaveLength(1)
    })

    it('图片校验：尺寸与比例不符被拒', () => {
      const target = create()
      const stub = createUploadTransportStub()
      target.setReady(true)
      target.setTransport(stub.transport)
      target.setOptions({ kind: 'image', imageOptions: { aspect: 1 } })
      const result = target.acceptFiles([
        { file: 'f', meta: { ...FILE_CONTRACT_IMAGE, dimension: { width: 2, height: 1 } } },
      ])
      expect(result.rejected[0]?.code).toBe(50102)
      expect(stub.calls).toEqual([])
    })

    it('预览与下载：无能力时回落已有地址且零请求', async () => {
      const target = create()
      target.setValue(['f1'])
      await target.resolveFiles()
      expect(target.requestCount).toBe(0)
      const url = await target.previewUrlOf('f1')
      expect(url).toBeUndefined()
      await expect(target.downloadFile('f1')).resolves.toBeUndefined()
      expect(target.summary()).toContain('f1')
    })
  })
}
