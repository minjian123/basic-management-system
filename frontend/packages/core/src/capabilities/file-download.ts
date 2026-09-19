/**
 * 下载触发能力基类：取址 / 触发下载 / 失效重取 / 降级重试（模板、错误明细、导出结果共用）。
 *
 * **取址顺序**：入参 `url` → 宿主取址（`fetcher`）→ 预签名回退（组合的 `BasePresignedUrl`）。
 * **触发手段**（`trigger`）由件层注入（核心不触 DOM）；未注入即占位：不动作、不请求。
 */

import { BaseComponent } from '../base/BaseComponent'
import type { BasePresignedUrl } from './presigned-url'

/** 下载阶段。 */
export type DownloadPhase = 'idle' | 'fetching' | 'done' | 'failed'

/** 下载请求（取址与命名）。 */
export interface DownloadRequest {
  /** 业务标识（后端路径段）。 */
  biz?: string
  /** 用途（模板 / 错误明细 / 导出结果，由调用方约定）。 */
  kind?: string
  /** 直连 URL（优先）。 */
  url?: string
  /** 一次性令牌（后端按首次结果生成）。 */
  token?: string
  /** 文件名（调用方按领域函数传入）。 */
  filename?: string
}

/** 下载结果。 */
export interface DownloadResult {
  /** 取到的 URL（blob 通路时为空串）。 */
  url: string
  /** 实际文件名。 */
  filename: string
  /** 附加上报文案（可选）。 */
  message?: string
}

/** 取址结果（URL 或二进制载荷）。 */
export interface DownloadSource {
  /** URL。 */
  url?: string
  /** 二进制载荷（件层解释，核心不触 DOM）。 */
  blob?: unknown
  /** 文件名。 */
  filename?: string
}

/** 取址处理函数（宿主注入）。 */
export type DownloadFetcher = (input: DownloadRequest) => Promise<DownloadSource | undefined>

/** 浏览器触发处理函数（件层 / 宿主注入；未注入即占位）。 */
export type DownloadTrigger = (input: { url?: string; blob?: unknown; filename: string }) => void

/** 占位文案（未注入触发手段）。 */
export const DOWNLOAD_PLACEHOLDER_TEXT = '下载未就绪（占位）'

/** 下载触发能力基类（抽象）。 */
export abstract class BaseFileDownload extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'file-download'
  /** 依赖能力键（预签名取址回退）。 */
  override readonly depends = ['presigned-url']
  /** 下载阶段。 */
  phase: DownloadPhase = 'idle'
  /** 最近取到的 URL。 */
  url = ''
  /** 最近使用的文件名。 */
  filename = ''
  /** 失败文案。 */
  errorMessage = ''
  /** 最近一次下载结果。 */
  lastResult: DownloadResult | undefined
  /** 预签名能力（取址回退；未注入不影响直连 URL 与取址通路）。 */
  presigned: BasePresignedUrl | undefined
  /** 取址处理函数（宿主注入）。 */
  fetcher: DownloadFetcher | undefined
  /** 浏览器触发处理函数（件层注入；未注入即占位）。 */
  trigger: DownloadTrigger | undefined
  /** 上次请求（重试用）。 */
  #pending: DownloadRequest | undefined

  /** 是否就绪（已注入触发手段）。 */
  get ready(): boolean {
    return this.trigger !== undefined
  }

  /** 是否下载中。 */
  get busy(): boolean {
    return this.phase === 'fetching'
  }

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /**
   * 下载（取址 → 触发）。
   *
   * @param input 下载请求。
   * @returns 下载结果；占位 / 下载中 / 取址失败时返回 `undefined`。
   */
  async download(input: DownloadRequest = {}): Promise<DownloadResult | undefined> {
    if (this.trigger === undefined) {
      this.errorMessage = DOWNLOAD_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    if (this.busy) {
      return undefined
    }
    this.#pending = { ...input }
    this.phase = 'fetching'
    this.errorMessage = ''
    this.touch()
    try {
      const source = await this.resolve(input)
      const url = source.url ?? ''
      const filename = input.filename ?? source.filename ?? this.filename
      if (url === '' && source.blob === undefined) {
        return this.fail('下载地址不可用')
      }
      this.trigger(url === '' ? { blob: source.blob, filename } : { url, blob: source.blob, filename })
      const result: DownloadResult = { url, filename }
      this.url = url
      this.filename = filename
      this.lastResult = result
      this.phase = 'done'
      this.touch()
      return result
    } catch (error) {
      return this.fail(error instanceof Error && error.message !== '' ? error.message : '下载失败')
    }
  }

  /**
   * 重试上次失败的下载。
   *
   * @returns 下载结果；非失败态或无上次请求时返回 `undefined`。
   */
  async retry(): Promise<DownloadResult | undefined> {
    if (this.phase !== 'failed' || this.#pending === undefined) {
      return undefined
    }
    return this.download(this.#pending)
  }

  /** 复位（清阶段、错误与上次请求；保留注入的触发与取址）。 */
  reset(): void {
    this.phase = 'idle'
    this.errorMessage = ''
    this.url = ''
    this.filename = ''
    this.lastResult = undefined
    this.#pending = undefined
    this.touch()
  }

  /**
   * 取址（入参 URL → 宿主取址 → 预签名回退）。
   *
   * @param input 下载请求。
   * @returns 取址结果（皆无时为空对象）。
   */
  private async resolve(input: DownloadRequest): Promise<DownloadSource> {
    if (input.url !== undefined && input.url !== '') {
      return { url: input.url, filename: input.filename }
    }
    if (this.fetcher !== undefined) {
      const fetched = await this.fetcher(input)
      if (fetched !== undefined && (fetched.url !== undefined || fetched.blob !== undefined)) {
        return fetched
      }
    }
    if (this.presigned !== undefined) {
      const url = await this.presigned.get()
      if (url !== undefined && url !== '') {
        return { url, filename: input.filename }
      }
    }
    return {}
  }

  /**
   * 失败处置（阶段置失败、写文案）。
   *
   * @param message 失败文案。
   */
  private fail(message: string): undefined {
    this.phase = 'failed'
    this.errorMessage = message
    this.touch()
    return undefined
  }

  /** 通知变更（已释放时跳过）。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
