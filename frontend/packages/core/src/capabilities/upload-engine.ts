/**
 * 上传引擎能力基类：分片 / 秒传 / 断点续传 / 进度 / 取消（上传器由宿主注入，占位不请求）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 上传进度回传（0 ~ 100）。 */
export type UploadProgressReporter = (percent: number) => void

/** 上传器（宿主注入；返回对象键；`report` 回传可量化进度）。 */
export type Uploader<TFile> = (file: TFile, report: UploadProgressReporter) => Promise<string>

/**
 * 进度夹取（0 ~ 100 整数；非法值回落 0）。
 *
 * @param percent 原始进度。
 * @returns 夹取后的进度。
 */
function clampProgress(percent: number): number {
  if (!Number.isFinite(percent)) {
    return 0
  }
  return Math.min(100, Math.max(0, Math.round(percent)))
}

/** 上传引擎能力基类（抽象）。 */
export abstract class BaseUploadEngine<TFile = unknown> extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'upload-engine'
  /** 依赖能力键（预签名）。 */
  override readonly depends = ['presigned-url']
  /** 分片大小（字节）。 */
  chunkSize = 5 * 1024 * 1024
  /** 单文件大小上限（字节；0 表示不限）。 */
  maxSize = 0
  /** 上传进度（0 ~ 100）。 */
  progress = 0
  /** 上传器（未注入则占位不请求）。 */
  uploader: Uploader<TFile> | undefined
  /** 中断钩子（宿主注入；`cancel()` 时调用，用于中断在途请求）。 */
  abort: (() => void) | undefined
  /** 是否已被取消（在途状态）。 */
  #canceled = false

  /** 是否处于已取消状态（在途请求已请求中断）。 */
  get canceled(): boolean {
    return this.#canceled
  }

  /**
   * 上传文件（未注入上传器则占位返回 `undefined`）。
   *
   * 进度经 `report` 回传并夹取到 0 ~ 100；失败向上抛错（**保留当前进度**，不置满）；取消后以 `undefined` 结束且不再更新进度。
   *
   * @param file 文件。
   * @returns 对象键；取消或占位时返回 `undefined`。
   */
  async upload(file: TFile): Promise<string | undefined> {
    if (this.uploader === undefined) {
      return undefined
    }
    this.#canceled = false
    this.progress = 0
    this.touch()
    const key = await this.uploader(file, (percent) => {
      if (this.#canceled) {
        return
      }
      this.progress = clampProgress(percent)
      this.touch()
    })
    if (this.#canceled) {
      return undefined
    }
    this.progress = 100
    this.touch()
    return key
  }

  /** 取消上传（中断在途请求并复位进度）。 */
  cancel(): void {
    this.#canceled = true
    this.abort?.()
    this.progress = 0
    this.touch()
  }

  /** 通知变更（已释放时跳过）。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
