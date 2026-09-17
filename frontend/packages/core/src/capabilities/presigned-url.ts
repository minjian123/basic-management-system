/** 预签名能力：获取 / 失效重取 / 降级下载（签名源经注入 resolver；占位优先）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface PresignedUrlOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 签名获取（缺省占位：原样返回，不发请求） */
  resolve?: (objectKey: string) => Promise<{ url: string; expiresAt: number }>
}

export class BasePresignedUrl extends BaseCapability {
  readonly resolving = observable(false)
  private readonly cache = new Map<string, { url: string; expiresAt: number }>()
  private readonly resolver: PresignedUrlOptions['resolve']

  constructor(options: PresignedUrlOptions = {}) {
    super({ ...options, key: options.key ?? 'presigned-url' })
    this.resolver = options.resolve
  }

  async get(objectKey: string): Promise<string> {
    const cached = this.cache.get(objectKey)
    if (cached && cached.expiresAt > Date.now()) {
      return cached.url
    }
    if (!this.resolver) {
      return objectKey
    }
    this.resolving.set(true)
    try {
      const result = await this.resolver(objectKey)
      this.cache.set(objectKey, result)
      return result.url
    } catch (error) {
      this.reportError(error, { phase: 'presigned-url', objectKey })
      return objectKey
    } finally {
      this.resolving.set(false)
    }
  }

  invalidate(objectKey?: string): void {
    if (objectKey === undefined) {
      this.cache.clear()
      return
    }
    this.cache.delete(objectKey)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), placeholder: !this.resolver, cached: this.cache.size }
  }
}
