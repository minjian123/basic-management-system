/**
 * 数据契约基类（契约层）：不可变语义与稳定序列化。
 */

import { BaseObject } from '../base/BaseObject'
import { stableStringify } from '../domain/serialize'

/** 数据对象基类（抽象）。 */
export abstract class BaseDataObject extends BaseObject {
  /**
   * 稳定序列化（键排序，便于比对与缓存键）。
   *
   * @returns 稳定 JSON 字符串。
   */
  toStableJSON(): string {
    return stableStringify(this)
  }
}
