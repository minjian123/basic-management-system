/** 语言上下文能力：locale / 时区 / 格式上下文（切换与持久化随后续接入）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface LocaleOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  locale?: string
  timezone?: string
}

export class BaseLocale extends BaseCapability {
  readonly locale = observable('zh-CN')
  readonly timezone = observable('Asia/Shanghai')

  constructor(options: LocaleOptions = {}) {
    super({ ...options, key: options.key ?? 'locale' })
    this.locale.set(options.locale ?? 'zh-CN')
    this.timezone.set(options.timezone ?? 'Asia/Shanghai')
  }

  setLocale(locale: string): void {
    this.locale.set(locale)
  }

  setTimezone(timezone: string): void {
    this.timezone.set(timezone)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), locale: this.locale.get(), timezone: this.timezone.get() }
  }
}
