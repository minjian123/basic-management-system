/** 本地二次缓存通道：`localStorage` 单一落点（不可用环境返回 `undefined`，核心不触浏览器 API）。 */

import type { DictStorageChannel } from '@bms/core'

/** 探测键（读写后即删，验证可用性）。 */
const PROBE_KEY = 'bms:dict:probe'

/**
 * 创建 localStorage 通道（能力探测失败 / 隐私模式返回 `undefined`）。
 *
 * @returns 通道实例；不可用 `undefined`。
 */
function createLocalStorageChannel(): DictStorageChannel | undefined {
  try {
    const storage = globalThis.localStorage
    if (storage === undefined || storage === null) {
      return undefined
    }
    storage.setItem(PROBE_KEY, '1')
    storage.removeItem(PROBE_KEY)
    return {
      read: (key: string): string | undefined => {
        try {
          return storage.getItem(key) ?? undefined
        } catch {
          return undefined
        }
      },
      write: (key: string, value: string): void => {
        try {
          storage.setItem(key, value)
        } catch {
          // 配额 / 隐私模式：静默降级（不阻断）
        }
      },
      remove: (key: string): void => {
        try {
          storage.removeItem(key)
        } catch {
          // 静默降级
        }
      },
    }
  } catch {
    return undefined
  }
}

/** 本地二次缓存通道（不可用环境为 `undefined`）。 */
export const localStorageDictChannel: DictStorageChannel | undefined = createLocalStorageChannel()
