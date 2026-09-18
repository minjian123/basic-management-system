/**
 * 上传引擎能力基类：分片 / 秒传 / 断点续传 / 进度 / 取消（上传器由宿主注入，占位不请求）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 上传器（宿主注入；返回对象键）。 */
export type Uploader<TFile> = (file: TFile) => Promise<string>

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

  /**
   * 上传文件（未注入上传器则占位返回 `undefined`）。
   *
   * @param file 文件。
   * @returns 对象键。
   */
  async upload(file: TFile): Promise<string | undefined> {
    if (this.uploader === undefined) {
      return undefined
    }
    this.progress = 0
    const key = await this.uploader(file)
    this.progress = 100
    return key
  }

  /** 取消上传（复位进度）。 */
  cancel(): void {
    this.progress = 0
  }
}
