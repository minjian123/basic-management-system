/**
 * 实体契约基类：在数据对象之上加标识 / 版本 / 软删除回显。
 */

import { BaseDataObject } from './data-object'

/** 实体基类（抽象）。 */
export abstract class BaseEntity extends BaseDataObject {
  /** 主键（雪花 ID 以字符串传输，避免 JS 精度丢失）。 */
  abstract readonly id: string
  /** 乐观锁版本（对应后端实体 `version`；此处命名避开总基类根字段 `version`）。 */
  readonly recordVersion?: number
  /** 软删除时间（回显；非空即视为已删除）。 */
  readonly deletedAt?: string | null

  /** 是否已软删除。 */
  get isDeleted(): boolean {
    return this.deletedAt != null
  }
}
