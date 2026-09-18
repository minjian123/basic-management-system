/**
 * 插件基类：可替换实现的装配语义（固定三段第 3 层，对齐后端同名基类）。
 *
 * 承载能力键 / 实现名 / 契约版本 / 生命周期 / 元信息；只做装配语义，不含具体实现。
 * 注册与解析调用统一注册表（02_05）。
 */

import { BaseCapability } from './capability'

/** 契约版本默认值（自 `0.1.0` 起，对齐后端）。 */
export const DEFAULT_CONTRACT_VERSION = '0.1.0'

/** 插件基类（抽象）。 */
export abstract class BasePluggable extends BaseCapability {
  /** 插件键（与能力键一致）。 */
  abstract readonly pluginKey: string
  /** 实现名（内部实现名 / `null` 占位）。 */
  abstract readonly pluginName: string
  /** 契约版本。 */
  readonly contractVersion: string = DEFAULT_CONTRACT_VERSION

  /** 能力键 = 插件键（满足能力域基类抽象成员）。 */
  override get key(): string {
    return this.pluginKey
  }

  /** 装配钩子（缺省空实现）。 */
  setup(): void {}

  /** 元信息描述：`插件键:实现名@契约版本`。 */
  override describe(): string {
    return `${this.pluginKey}:${this.pluginName}@${this.contractVersion}`
  }
}
