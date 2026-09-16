/** 权限上下文能力：权限码集合与判定（集合来源经注入；占位空集 = 全量降级）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface AccessOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  codes?: readonly string[]
}

export class BaseAccess extends BaseCapability {
  readonly codes = observable<readonly string[]>([])
  readonly placeholder: boolean

  constructor(options: AccessOptions = {}) {
    super({ ...options, key: options.key ?? 'access' })
    this.codes.set(options.codes ?? [])
    this.placeholder = options.codes === undefined
  }

  has(code: string): boolean {
    return this.codes.get().includes(code)
  }

  hasAny(codes: readonly string[]): boolean {
    return codes.some((code) => this.has(code))
  }

  hasAll(codes: readonly string[]): boolean {
    return codes.every((code) => this.has(code))
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), placeholder: this.placeholder, count: this.codes.get().length }
  }
}
