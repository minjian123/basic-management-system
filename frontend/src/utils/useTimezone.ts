/**
 * 用户时区组合式：读取 / 切换时区偏好，并同步格式化默认基准。
 *
 * 取值优先级：显式入参 > localStorage（`bms_timezone`，`persist !== false`）> 浏览器时区。
 * **占位先行**：`sys_user.timezone` 接口未接入（`isPlaceholder` 恒 true）；登录装配后经入参 / `setTimezone` 注入即接。
 */

import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { configureFormatDefaults } from './format'

/** 时区本地持久化键（占位；后端偏好接入后以远端为准） */
export const TIMEZONE_STORAGE_KEY = 'bms_timezone'

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

function loadStored(): string | undefined {
  try {
    return localStorage.getItem(TIMEZONE_STORAGE_KEY) ?? undefined
  } catch {
    return undefined
  }
}

export interface UseTimezoneReturn {
  readonly timezone: string
  setTimezone: (next: string) => void
  /** 用户偏好接口未接入（占位） */
  readonly isPlaceholder: boolean
}

/**
 * 获取用户时区能力。
 *
 * 用法：`const { timezone, setTimezone } = useTimezone()`；变更即同步格式化默认基准（页面经响应式引用自动更新）。
 */
export function useTimezone(
  options: { timezone?: MaybeRefOrGetter<string>; persist?: boolean } = {},
): UseTimezoneReturn {
  const persist = options.persist !== false
  const explicit = options.timezone !== undefined ? toValue(options.timezone) : undefined
  const initial = explicit ?? (persist ? loadStored() : undefined) ?? browserTimezone()
  const timezone = ref(initial)
  configureFormatDefaults({ timezone: timezone.value })
  watch(
    timezone,
    (next) => {
      configureFormatDefaults({ timezone: next })
      if (persist) {
        try {
          localStorage.setItem(TIMEZONE_STORAGE_KEY, next)
        } catch {
          // 存储不可用（隐私模式等）：仅内存生效，不阻断
        }
      }
    },
    { flush: 'sync' },
  )
  return {
    get timezone() {
      return timezone.value
    },
    setTimezone: (next: string) => {
      timezone.value = next
    },
    isPlaceholder: true,
  }
}
