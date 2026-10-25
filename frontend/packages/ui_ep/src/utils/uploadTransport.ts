/**
 * 上传通路：HTTP 内建实现 + 注册表默认实例（`fetch` / `FormData` / `Blob` 单一落点）。
 *
 * 端点与后端对象存储扩展基座（`02-4-18`，`/api/v1/files/*`）及冻结契约缺口同源：
 * 秒传 `GET /files/dedup`、整包 `POST /files`、分片 `POST /files/uploads` +
 * `PUT /files/uploads/{id}/parts/{no}` + `POST /files/uploads/{id}/complete` + `DELETE /files/uploads/{id}`、
 * 已传分片 `GET /files/uploads/{id}/parts`、批量元数据 `GET /files?ids=`、
 * 下载 / 预览预签名 `GET /files/{id}/download-url` / `preview-url`；
 * 宿主可经 `registerUploadTransport` 登记定制实现或覆盖内建键。
 */

import {
  BaseError,
  BaseUploadTransport,
  UploadTransportProvider,
  UploadTransportRegistry,
  buildDedupQuery,
  buildMultipartInit,
  buildResolveQuery,
  fileExtOf,
  type UploadAbortSignal,
  type UploadCheckQuery,
  type UploadHashQuery,
  type UploadInitQuery,
  type UploadPartQuery,
  type UploadPresignQuery,
  type UploadResolveQuery,
  type UploadSessionQuery,
  type UploadTransportOptions,
  type UploadWholeQuery,
} from '@bms/core'

import { hashFile } from './fileHash'

/** 链路内默认上传通路注册表实例（宿主可登记定制实现或覆盖内建键）。 */
export const uploadTransportRegistry = new UploadTransportRegistry()

/**
 * 登记上传通路实现。
 *
 * @param key 通路键（同键拒重）。
 * @param create 通路工厂。
 */
export function registerUploadTransport(
  key: string,
  create: (options: UploadTransportOptions) => BaseUploadTransport | Promise<BaseUploadTransport>,
): void {
  uploadTransportRegistry.register(new UploadTransportProvider(key, create))
}

/** HTTP 内建上传通路（未覆盖的方法不请求）。 */
class HttpUploadTransport extends BaseUploadTransport {
  /** 实现名。 */
  override readonly pluginName: string = 'http'
  /** 装载选项（端点 / 请求头）。 */
  readonly #options: UploadTransportOptions

  /**
   * 构造 HTTP 通路。
   *
   * @param options 装载选项。
   */
  constructor(options: UploadTransportOptions = {}) {
    super()
    this.#options = options
  }

  /**
   * 整文件（含每片）哈希（本地计算，无请求）。
   *
   * @param query 哈希入参。
   * @returns 哈希结果。
   */
  override async hash(query: UploadHashQuery): Promise<unknown> {
    return hashFile(query.file, {
      ...(query.partSize === undefined ? {} : { partSize: query.partSize }),
      ...(query.signal === undefined ? {} : { signal: query.signal }),
    })
  }

  /**
   * 秒传判定。
   *
   * @param query 判定入参。
   * @returns 既有对象引用或 `null`。
   */
  override async check(query: UploadCheckQuery): Promise<unknown> {
    return this.#request('GET', '/files/dedup', buildDedupQuery(query.sha256, query.size))
  }

  /**
   * 整包上传（表单字段 `file`）。
   *
   * @param query 上传入参。
   * @returns 对象元数据。
   */
  override async uploadWhole(query: UploadWholeQuery): Promise<unknown> {
    const form = new FormData()
    form.append('file', query.file as Blob, query.name)
    if (query.sha256 !== undefined && query.sha256 !== '') {
      form.append('sha256', query.sha256)
    }
    query.report?.(0)
    const result = await this.#request('POST', '/files', form, query.signal)
    query.report?.(100)
    return result
  }

  /**
   * 分片初始化（对象键缺省按 `files/{yyyyMMdd}/{uuid}{ext}` 生成）。
   *
   * @param query 初始化入参。
   * @returns 会话。
   */
  override async initiate(query: UploadInitQuery): Promise<unknown> {
    const key = query.key !== undefined && query.key !== '' ? query.key : defaultObjectKey(query.name)
    return this.#request(
      'POST',
      '/files/uploads',
      buildMultipartInit({
        key,
        size: query.size,
        ...(query.sha256 === undefined ? {} : { sha256: query.sha256 }),
        ...(query.mime === '' ? {} : { mime: query.mime }),
        ...(query.partSize === undefined ? {} : { partSize: query.partSize }),
      }),
    )
  }

  /**
   * 分片上传（表单字段 `data`，切片归本实现）。
   *
   * @param query 分片入参。
   * @returns 分片结果。
   */
  override async uploadPart(query: UploadPartQuery): Promise<unknown> {
    const blob = query.file as Blob | undefined
    if (blob === undefined || blob === null || typeof blob.slice !== 'function') {
      throw new BaseError(50104, '文件对象不可用')
    }
    const form = new FormData()
    form.append('data', blob.slice(query.start, query.end), `part-${query.partNo}`)
    return this.#request(
      'PUT',
      `/files/uploads/${encodeURIComponent(query.uploadId)}/parts/${query.partNo}`,
      form,
      query.signal,
    )
  }

  /**
   * 分片合并。
   *
   * @param query 会话入参。
   * @returns 对象元数据。
   */
  override async complete(query: UploadSessionQuery): Promise<unknown> {
    return this.#request('POST', `/files/uploads/${encodeURIComponent(query.uploadId)}/complete`, {})
  }

  /**
   * 取消会话（清理临时分片）。
   *
   * @param query 会话入参。
   * @returns 无数据体。
   */
  override async abort(query: UploadSessionQuery): Promise<unknown> {
    return this.#request('DELETE', `/files/uploads/${encodeURIComponent(query.uploadId)}`, {})
  }

  /**
   * 已传分片查询（断点续传）。
   *
   * @param query 会话入参。
   * @returns 已传分片列表。
   */
  override async listParts(query: UploadSessionQuery): Promise<unknown> {
    return this.#request('GET', `/files/uploads/${encodeURIComponent(query.uploadId)}/parts`, {})
  }

  /**
   * 批量元数据（一次批量，避免 N+1）。
   *
   * @param query 批量入参。
   * @returns 文件引用列表。
   */
  override async resolveFiles(query: UploadResolveQuery): Promise<unknown> {
    return this.#request('GET', '/files', buildResolveQuery(query.ids))
  }

  /**
   * 下载 / 预览预签名。
   *
   * @param query 预签名入参。
   * @returns 预签名结果（`url` / `expires_in`）。
   */
  override async presign(query: UploadPresignQuery): Promise<unknown> {
    const path = query.purpose === 'preview' ? 'preview-url' : 'download-url'
    return this.#request('GET', `/files/${encodeURIComponent(query.fileId)}/${path}`, {
      ...(query.expiresIn === undefined ? {} : { expires_in: query.expiresIn }),
    })
  }

  /**
   * 统一请求并解响应包装。
   *
   * @param method 方法。
   * @param path 路径（相对端点前缀）。
   * @param payload 查询参数（GET / DELETE）或请求体（POST / PUT；`FormData` 直传）。
   * @param abortSignal 中断信号（可选）。
   * @returns 数据体（无 `fetch` 能力时降级 `undefined`）。
   */
  async #request(
    method: 'GET' | 'POST' | 'PUT' | 'DELETE',
    path: string,
    payload: Record<string, unknown> | FormData,
    abortSignal?: UploadAbortSignal,
  ): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      return undefined
    }
    const endpoint = (this.#options.endpoint ?? '/api/v1').replace(/\/+$/, '')
    const headers = typeof this.#options.headers === 'function' ? this.#options.headers() : this.#options.headers
    const watch = watchAbort(abortSignal)
    try {
      const init: RequestInit = { method, headers: { ...(headers ?? {}) }, ...(watch.signal === undefined ? {} : { signal: watch.signal }) }
      let url = `${endpoint}${path}`
      if (payload instanceof FormData) {
        init.body = payload
      } else if (method === 'GET' || method === 'DELETE') {
        const search = new URLSearchParams()
        for (const [key, value] of Object.entries(payload)) {
          if (value === undefined || value === null || value === false) {
            continue
          }
          search.set(key, value === true ? 'true' : String(value))
        }
        url = search.size > 0 ? `${url}?${search.toString()}` : url
      } else {
        init.headers = { 'Content-Type': 'application/json', ...(headers ?? {}) }
        init.body = JSON.stringify(payload)
      }
      const response = await fetchFn(url, init)
      if (!response.ok) {
        throw new BaseError(50104, '文件上传服务不可用')
      }
      return unwrapResponse(await response.json())
    } finally {
      watch.dispose()
    }
  }
}

/**
 * 创建 HTTP 内建上传通路。
 *
 * @param options 装载选项。
 * @returns 通路实例。
 */
export function createHttpUploadTransport(options: UploadTransportOptions = {}): BaseUploadTransport {
  return new HttpUploadTransport(options)
}

/** 登记内建 HTTP 通路（默认键，宿主可覆盖）。 */
registerUploadTransport('http', createHttpUploadTransport)

/**
 * 生成缺省对象键（`files/{yyyyMMdd}/{uuid}{ext}`；租户前缀由实现侧按需拼接）。
 *
 * @param name 文件名。
 * @returns 对象键。
 */
function defaultObjectKey(name: string): string {
  const now = new Date()
  const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  const ext = fileExtOf(name)
  return `files/${date}/${randomId()}${ext === '' ? '' : `.${ext}`}`
}

/**
 * 随机标识（`crypto.randomUUID` 优先，能力缺失回退时间戳 + 随机数）。
 *
 * @returns 随机标识。
 */
function randomId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`
}

/**
 * 桥接中断信号（结构信号 → `AbortSignal`；轮询检测中断）。
 *
 * @param signal 结构中断信号（可选）。
 * @returns `AbortSignal` 与释放函数。
 */
function watchAbort(signal?: UploadAbortSignal): { signal: AbortSignal | undefined; dispose: () => void } {
  if (signal === undefined || typeof AbortController !== 'function') {
    return { signal: undefined, dispose: () => {} }
  }
  const controller = new AbortController()
  const timer = setInterval(() => {
    if (signal.aborted) {
      controller.abort()
    }
  }, 50)
  return {
    signal: controller.signal,
    dispose: () => clearInterval(timer),
  }
}

/**
 * 解统一响应包装（`{ code, message, data }`；非包装原样返回；业务码非 0 / 200 抛错）。
 *
 * @param payload 原始响应体。
 * @returns 数据体。
 */
function unwrapResponse(payload: unknown): unknown {
  if (payload !== null && typeof payload === 'object' && !Array.isArray(payload)) {
    const record = payload as { code?: unknown; message?: unknown; data?: unknown }
    if (typeof record.code === 'number') {
      if (record.code !== 0 && record.code !== 200) {
        throw new BaseError(record.code, typeof record.message === 'string' ? record.message : '')
      }
      return record.data
    }
  }
  return payload
}
