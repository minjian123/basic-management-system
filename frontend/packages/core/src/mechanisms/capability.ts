/**
 * 能力域基类：能力键声明与依赖登记机制（固定三段第 2 层，对齐后端同名基类）。
 *
 * 只承载「能力如何声明」——键（kebab-case）、依赖清单与元信息；不含 UI 与业务语义。
 * 依赖的单向校验与登记表（`capabilities/manifest.ts`）由 02_03 承接。
 */

import { BaseObject } from '../base/BaseObject'

/** 能力域基类（抽象）。 */
export abstract class BaseCapability extends BaseObject {
  /** 能力键（kebab-case，域内唯一）。 */
  abstract readonly key: string
  /** 依赖的能力键（登记 / 单向校验由 02_03 承接）。 */
  readonly depends: readonly string[] = []

  /** 元信息描述。 */
  describe(): string {
    return `${this.key}（能力域基类）`
  }
}
