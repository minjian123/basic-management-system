/** 宿主能力装配的组合式取用入口（页面 / 核对页统一经此取默认源）。 */

import { getAppCapabilities, type AppCapabilities } from '@/capabilities'

/**
 * 取宿主已装配能力（未装配即抛 `19001`）。
 *
 * @returns 宿主能力集合。
 */
export function useAppCapabilities(): AppCapabilities {
  return getAppCapabilities()
}
