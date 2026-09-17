/** 表单元数据能力：加载 / 缓存 / 版本比对（元数据源经注入 loader；占位优先）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface FormMetaOptions<T = unknown> extends Omit<CapabilityOptions, 'key'> {
  key?: string
  loader?: () => Promise<T>
}

export class BaseFormMeta<T = unknown> extends BaseCapability {
  readonly meta = observable<T | undefined>(undefined)
  /** 元数据版本（域语义名，避让根系 `version`） */
  readonly metaVersion = observable('')
  /** 加载中（域语义名，避让组件根 `loading`） */
  readonly pending = observable(false)
  private readonly loader: FormMetaOptions<T>['loader']

  constructor(options: FormMetaOptions<T> = {}) {
    super({ ...options, key: options.key ?? 'form-meta' })
    this.loader = options.loader
  }

  async load(version = ''): Promise<T | undefined> {
    if (this.meta.get() !== undefined && this.metaVersion.get() === version) {
      return this.meta.get()
    }
    if (!this.loader) {
      return undefined
    }
    this.pending.set(true)
    try {
      const meta = await this.loader()
      this.meta.set(meta)
      this.metaVersion.set(version)
      return meta
    } finally {
      this.pending.set(false)
    }
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), placeholder: !this.loader }
  }
}
