/**
 * 占位三件（对齐后端占位）：占位标记 / 空实现 / 未实现桩。
 *
 * 占位不请求、不写缓存、无副作用；未实现调用统一抛 `BaseError(NOT_IMPLEMENTED)`。
 */

import { BaseObject } from '../base/BaseObject'
import { BaseError } from './error'
import { ErrorCodes } from './error-codes'

/** 占位原因：待回补 / 空值 / 未实现。 */
export type PlaceholderReason = 'pending' | 'null' | 'stub'

/** 占位基类（抽象）。 */
export abstract class BasePlaceholder extends BaseObject {
  /** 占位标记（便于启动校验与测试断言）。 */
  readonly placeholder = true
  /** 占位原因。 */
  abstract readonly reason: PlaceholderReason

  /** 占位描述。 */
  describe(): string {
    return `${this.constructor.name}（占位：${this.reason}）`
  }
}

/** 空实现（Null Object）：实现全部契约但无副作用。 */
export abstract class BaseNullObject extends BasePlaceholder {
  readonly reason = 'null' as const
}

/** 未实现桩：调用未实现能力统一抛错。 */
export abstract class BaseStub extends BasePlaceholder {
  readonly reason = 'stub' as const

  /**
   * 构造统一的未实现异常。
   *
   * @param feature 未实现的功能点（可选）。
   */
  protected notImplemented(feature = ''): never {
    throw new BaseError(
      ErrorCodes.NOT_IMPLEMENTED,
      `${this.constructor.name} 尚未实现${feature ? `：${feature}` : ''}`,
    )
  }
}
