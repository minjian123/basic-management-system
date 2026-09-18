/**
 * 用户 / 组织展示能力基类：姓名 / 头像 / 状态 / 部门路径。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 用户状态。 */
export type UserStatus = 'active' | 'disabled' | 'locked'

/** 用户展示信息。 */
export interface UserDisplayInfo {
  /** 用户标识。 */
  id: string
  /** 姓名。 */
  name: string
  /** 头像地址。 */
  avatar?: string
  /** 状态。 */
  status?: UserStatus
  /** 部门路径。 */
  deptPath?: string
}

/** 用户展示能力基类（抽象）。 */
export abstract class BaseUserDisplay extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'user-display'
  /** 当前用户信息。 */
  user: UserDisplayInfo | undefined

  /**
   * 设置当前用户信息。
   *
   * @param user 用户信息（缺省清空）。
   */
  setUser(user: UserDisplayInfo | undefined): void {
    this.user = user
  }

  /** 姓名。 */
  get name(): string {
    return this.user?.name ?? ''
  }

  /** 头像地址。 */
  get avatar(): string | undefined {
    return this.user?.avatar
  }

  /** 状态。 */
  get status(): UserStatus | undefined {
    return this.user?.status
  }

  /** 部门路径。 */
  get deptPath(): string | undefined {
    return this.user?.deptPath
  }
}
