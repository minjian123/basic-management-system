/** 用户展示投影：把核心用户展示能力基类 `BaseUserDisplay` 投影为组合式（姓名 / 头像 / 状态 / 部门路径 + 成员花名册）。 */

import { BaseUserDisplay, type UserDisplayInfo, type UserStatus } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体用户展示（可实例化，花名册方法触发更新通知）。 */
class UserDisplayState extends BaseUserDisplay {
  override setUser(user: UserDisplayInfo | undefined): void {
    super.setUser(user)
    this.notifyLifecycle('update')
  }

  override setUsers(users: readonly UserDisplayInfo[] = []): void {
    super.setUsers(users)
    this.notifyLifecycle('update')
  }

  override mergeUsers(users: readonly UserDisplayInfo[]): void {
    super.mergeUsers(users)
    this.notifyLifecycle('update')
  }

  override clearUsers(): void {
    super.clearUsers()
    this.notifyLifecycle('update')
  }
}

/** `useBaseUserDisplay` 返回面。 */
export interface UseBaseUserDisplayResult {
  /** 用户展示基类实例。 */
  userDisplay: BaseUserDisplay
  /** 当前用户信息（响应式）。 */
  user: Ref<UserDisplayInfo | undefined>
  /** 姓名（响应式）。 */
  name: Ref<string>
  /** 头像地址（响应式）。 */
  avatar: Ref<string | undefined>
  /** 状态（响应式）。 */
  status: Ref<UserStatus | undefined>
  /** 部门路径（响应式）。 */
  deptPath: Ref<string | undefined>
  /** 成员花名册（响应式）。 */
  users: Ref<UserDisplayInfo[]>
  /** 设置用户信息。 */
  setUser: (user: UserDisplayInfo | undefined) => void
  /** 整体替换成员花名册。 */
  setUsers: (users: readonly UserDisplayInfo[]) => void
  /** 增量合并成员花名册。 */
  mergeUsers: (users: readonly UserDisplayInfo[]) => void
  /** 清空成员花名册。 */
  clearUsers: () => void
  /** 按 id 查找成员。 */
  findUser: (id: string) => UserDisplayInfo | undefined
  /** 按 id 取展示信息（缺失回退 `id` 并标记已删除）。 */
  displayOf: (id: string) => UserDisplayInfo
}

/**
 * 使用用户展示投影。
 *
 * @param initial 初始用户信息。
 * @returns 用户展示基类实例与响应式面。
 */
export function useBaseUserDisplay(initial?: UserDisplayInfo): UseBaseUserDisplayResult {
  const userDisplay = new UserDisplayState()
  if (initial) {
    userDisplay.setUser(initial)
  }

  const user = ref<UserDisplayInfo | undefined>(userDisplay.user)
  const name = ref(userDisplay.name)
  const avatar = ref(userDisplay.avatar)
  const status = ref(userDisplay.status)
  const deptPath = ref(userDisplay.deptPath)
  const users = ref<UserDisplayInfo[]>([...userDisplay.users])

  function sync(): void {
    user.value = userDisplay.user
    name.value = userDisplay.name
    avatar.value = userDisplay.avatar
    status.value = userDisplay.status
    deptPath.value = userDisplay.deptPath
    users.value = [...userDisplay.users]
  }

  const off = userDisplay.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    userDisplay,
    user,
    name,
    avatar,
    status,
    deptPath,
    users,
    setUser: (next) => userDisplay.setUser(next),
    setUsers: (next) => userDisplay.setUsers(next),
    mergeUsers: (next) => userDisplay.mergeUsers(next),
    clearUsers: () => userDisplay.clearUsers(),
    findUser: (id) => userDisplay.findUser(id),
    displayOf: (id) => userDisplay.displayOf(id),
  }
}
