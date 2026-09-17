/** 媒体形态能力：媒体加载状态机（idle / loading / loaded / error + 重试），依赖 `presigned-url`。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export type MediaState = 'idle' | 'loading' | 'loaded' | 'error'

export interface MediaOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 资源获取（预签名 / URL 解析由注入的 resolver 承担） */
  resolve?: (source: string) => Promise<string>
}

export class BaseMedia extends BaseCapability {
  readonly state = observable<MediaState>('idle')
  readonly url = observable('')
  readonly retryCount = observable(0)

  private readonly resolver: ((source: string) => Promise<string>) | undefined

  constructor(options: MediaOptions = {}) {
    super({ ...options, key: options.key ?? 'media' })
    this.resolver = options.resolve
  }

  async load(source: string): Promise<boolean> {
    this.state.set('loading')
    try {
      const url = this.resolver ? await this.resolver(source) : source
      this.url.set(url)
      this.state.set('loaded')
      return true
    } catch (error) {
      this.state.set('error')
      this.reportError(error, { phase: 'media-load', source })
      return false
    }
  }

  async retry(source: string): Promise<boolean> {
    this.retryCount.set(this.retryCount.get() + 1)
    return this.load(source)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), state: this.state.get() }
  }
}
