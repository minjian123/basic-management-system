/**
 * 字段权限组件基类（字段权限族）：`permVisible` / `editable` / `permRequired` 三态 + 脱敏。
 */

import { BaseFieldShell } from './field-shell'

/** 字段权限输入。 */
export interface FieldPermission {
  /** 是否可见。 */
  visible?: boolean
  /** 是否可编辑。 */
  editable?: boolean
  /** 是否必填。 */
  required?: boolean
  /** 是否脱敏。 */
  mask?: boolean
}

/** 字段权限组件基类（抽象）。 */
export abstract class BaseFieldPerm extends BaseFieldShell {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'field-perm'
  /** 权限可见。 */
  permVisible = true
  /** 权限可编辑。 */
  editable = true
  /** 权限必填（与标签必填分离，避免覆写冲突）。 */
  permRequired = false
  /** 是否脱敏。 */
  masked = false

  /** 是否渲染（不可见不渲染）。 */
  get rendered(): boolean {
    return this.permVisible
  }

  /** 生效禁用态（权限不可编辑即禁用）。 */
  get effectiveDisabled(): boolean {
    return this.disabled || !this.editable
  }

  /**
   * 应用字段权限（缺省项不变）。
   *
   * @param permission 字段权限。
   */
  applyPerm(permission: FieldPermission): void {
    if (permission.visible !== undefined) {
      this.permVisible = permission.visible
    }
    if (permission.editable !== undefined) {
      this.editable = permission.editable
    }
    if (permission.required !== undefined) {
      this.permRequired = permission.required
    }
    if (permission.mask !== undefined) {
      this.masked = permission.mask
    }
    this.notifyLifecycle('update')
  }
}
