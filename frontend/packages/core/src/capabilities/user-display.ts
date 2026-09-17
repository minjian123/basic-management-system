/** 用户 / 组织展示能力：姓名 / 头像 / 部门路径（解析经注入 resolver；占位优先）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'

export interface UserDisplayInfo {
  name: string
  avatar?: string
  department?: string
}

export interface UserDisplayOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  resolve?: (userId: string) => UserDisplayInfo | undefined
}

export class BaseUserDisplay extends BaseCapability {
  private readonly resolver: UserDisplayOptions['resolve']

  constructor(options: UserDisplayOptions = {}) {
    super({ ...options, key: options.key ?? 'user-display' })
    this.resolver = options.resolve
  }

  /** 展示信息（缺省占位：以 id 兜底，不发请求） */
  display(userId: string): UserDisplayInfo {
    return this.resolver?.(userId) ?? { name: userId }
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), placeholder: !this.resolver }
  }
}
