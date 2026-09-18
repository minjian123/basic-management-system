/**
 * Vue 绑定：把 `BaseAccess` 投影为组合式（权限判定薄适配）。
 */

import { computed, type ComputedRef } from 'vue'

import type { BaseAccess } from '@bms/core'

/** `useAccess` 返回面。 */
export interface UseAccessResult {
  /** 权限码清单。 */
  codes: ComputedRef<readonly string[]>
  /** 是否具备某权限码。 */
  has: (code: string) => boolean
  /** 是否具备任一权限码。 */
  hasAny: (codes: readonly string[]) => boolean
  /** 是否具备全部权限码。 */
  hasAll: (codes: readonly string[]) => boolean
}

/**
 * 投影权限上下文为组合式。
 *
 * @param source 权限上下文实例。
 * @returns 权限判定面。
 */
export function useAccess(source: BaseAccess): UseAccessResult {
  return {
    codes: computed(() => source.codes),
    has: (code) => source.has(code),
    hasAny: (codes) => source.hasAny(codes),
    hasAll: (codes) => source.hasAll(codes),
  }
}
