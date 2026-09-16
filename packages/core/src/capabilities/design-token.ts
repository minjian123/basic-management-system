/** 设计令牌能力：令牌读数统一入口（取值经注入 reader；核心不内置样式系统）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'

export interface DesignTokenReader {
  token(name: string): string
}

export interface DesignTokenOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  reader?: DesignTokenReader
}

export class BaseDesignToken extends BaseCapability {
  private readonly reader: DesignTokenReader | undefined

  constructor(options: DesignTokenOptions = {}) {
    super({ ...options, key: options.key ?? 'design-token' })
    this.reader = options.reader
  }

  /** 读令牌（缺省空串；渲染插件注入真实读取，如 CSS 变量） */
  token(name: string): string {
    return this.reader?.token(name) ?? ''
  }

  spacing(step: number): string {
    return this.token(`--bms-space-${step}`)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), placeholder: !this.reader }
  }
}
