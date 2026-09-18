/** 用户展示投影：把核心用户展示能力基类 `BaseUserDisplay` 投影为组合式（姓名 / 头像 / 状态 / 部门路径）。 */

import { BaseUserDisplay, type UserDisplayInfo, type UserStatus } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体用户展示（可实例化，`setUser` 触发更新通知）。 */
class UserDisplayState extends BaseUserDisplay {
  override setUser(user: UserDisplayInfo | undefined): void {
    super.setUser(user)
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
  /** 设置用户信息。 */
  setUser: (user: UserDisplayInfo | undefined) => void
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

  function sync(): void {
    user.value = userDisplay.user
    name.value = userDisplay.name
    avatar.value = userDisplay.avatar
    status.value = userDisplay.status
    deptPath.value = userDisplay.deptPath
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
    setUser: (next) => userDisplay.setUser(next),
  }
}
