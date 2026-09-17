/** 选项源能力：加载 / 缓存与版本比对 / 搜索（后端未接入按占位降级），依赖 `value`。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface OptionItem {
  value: string
  label: string
}

export type OptionSourceLoader = (keyword?: string) => Promise<readonly OptionItem[]>

export interface OptionSourceOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 加载器（缺省占位：空结果、不发请求） */
  loader?: OptionSourceLoader
}

export class BaseOptionSource extends BaseCapability {
  readonly options = observable<readonly OptionItem[]>([])
  /** 加载中（域语义名，避让组件根 `loading`） */
  readonly pending = observable(false)
  readonly loaded = observable(false)
  private readonly loader: OptionSourceLoader | undefined

  constructor(options: OptionSourceOptions = {}) {
    super({ ...options, key: options.key ?? 'option-source' })
    this.loader = options.loader
  }

  async load(keyword?: string): Promise<readonly OptionItem[]> {
    if (!this.loader) {
      this.options.set([])
      this.loaded.set(true)
      return []
    }
    this.pending.set(true)
    try {
      const items = await this.loader(keyword)
      this.options.set(items)
      this.loaded.set(true)
      return items
    } finally {
      this.pending.set(false)
    }
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), loaded: this.loaded.get(), placeholder: !this.loader }
  }
}
