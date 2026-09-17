/** 上传引擎能力：提交 / 进度 / 取消骨架（分片与秒传随后端接入），依赖 `presigned-url`。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export type UploadState = 'idle' | 'uploading' | 'done' | 'error' | 'canceled'

export interface UploadOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 实际传输（预签名 / 分片细节由注入的 transport 承担） */
  transport?: (file: unknown, onProgress: (percent: number) => void) => Promise<string>
}

export class BaseUploadEngine extends BaseCapability {
  readonly state = observable<UploadState>('idle')
  readonly progress = observable(0)
  readonly resultUrl = observable('')
  private canceled = false
  private readonly transport: UploadOptions['transport']

  constructor(options: UploadOptions = {}) {
    super({ ...options, key: options.key ?? 'upload-engine' })
    this.transport = options.transport
  }

  async upload(file: unknown): Promise<string | undefined> {
    this.canceled = false
    this.state.set('uploading')
    this.progress.set(0)
    try {
      const url = this.transport
        ? await this.transport(file, (percent) => this.progress.set(percent))
        : `stub://${String((file as { name?: string })?.name ?? 'file')}`
      if (this.canceled) {
        this.state.set('canceled')
        return undefined
      }
      this.resultUrl.set(url)
      this.state.set('done')
      return url
    } catch (error) {
      this.state.set('error')
      this.reportError(error, { phase: 'upload' })
      return undefined
    }
  }

  cancel(): void {
    this.canceled = true
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), state: this.state.get() }
  }
}
