/**
 * 用户 / 组织展示能力基类：姓名 / 头像 / 状态 / 部门路径，及成员花名册。
 *
 * 花名册（`users`）为向后兼容扩展：组织选择、消息内用户信息等按 id 批量展示的场景
 * 统一经本基类解析；既有 `user` / `setUser` / `name` / `avatar` / `status` / `deptPath` 不变。
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
  /** 已删除（批量回显未命中 / 出口 `exists=false`）。 */
  deleted?: boolean
}

/** 用户展示能力基类（抽象）。 */
export abstract class BaseUserDisplay extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'user-display'
  /** 当前用户信息。 */
  user: UserDisplayInfo | undefined
  /** 成员花名册（按 id 索引；组织选择等场景复用）。 */
  readonly users: UserDisplayInfo[] = []

  /**
   * 设置当前用户信息。
   *
   * @param user 用户信息（缺省清空）。
   */
  setUser(user: UserDisplayInfo | undefined): void {
    this.user = user
  }

  /**
   * 整体替换成员花名册。
   *
   * @param users 成员信息（缺省清空）。
   */
  setUsers(users: readonly UserDisplayInfo[] = []): void {
    this.users.splice(0, this.users.length, ...users.map((item) => ({ ...item })))
  }

  /**
   * 增量合并成员花名册（同 id 覆盖，新项追加）。
   *
   * @param users 成员信息。
   */
  mergeUsers(users: readonly UserDisplayInfo[]): void {
    for (const item of users) {
      const exist = this.users.find((user) => user.id === item.id)
      if (exist === undefined) {
        this.users.push({ ...item })
      } else {
        Object.assign(exist, item)
      }
    }
  }

  /** 清空成员花名册。 */
  clearUsers(): void {
    this.users.splice(0, this.users.length)
  }

  /**
   * 按 id 查找成员。
   *
   * @param id 用户标识。
   */
  findUser(id: string): UserDisplayInfo | undefined {
    return this.users.find((user) => user.id === id)
  }

  /**
   * 按 id 取展示信息（缺失回落 `id` 并标记已删除）。
   *
   * @param id 用户标识。
   */
  displayOf(id: string): UserDisplayInfo {
    return this.findUser(id) ?? { id, name: id, deleted: true }
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
