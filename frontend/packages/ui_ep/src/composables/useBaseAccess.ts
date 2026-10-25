/** 权限上下文投影：把核心权限上下文能力基类 `BaseAccess` 投影为组合式（权限码集合与判定）。 */

import { BaseAccess } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体权限上下文（可实例化）。 */
class AccessState extends BaseAccess {}

/** `useBaseAccess` 返回面。 */
export interface UseBaseAccessResult {
  /** 权限上下文基类实例。 */
  access: BaseAccess
  /** 权限码（响应式）。 */
  codes: Ref<string[]>
  /** 整体替换权限码。 */
  setCodes: (codes: Iterable<string>) => void
  /** 是否具备某权限码。 */
  has: (code: string) => boolean
  /** 是否具备任一权限码。 */
  hasAny: (codes: readonly string[]) => boolean
  /** 是否具备全部权限码。 */
  hasAll: (codes: readonly string[]) => boolean
  /** 权限判定（供菜单过滤等使用；空码视为公开）。 */
  canAccess: (code?: string) => boolean
}

/**
 * 使用权限上下文投影。
 *
 * @param codes 初始权限码。
 * @returns 权限基类实例与响应式面。
 */
export function useBaseAccess(codes: Iterable<string> = []): UseBaseAccessResult {
  const access = new AccessState()
  access.setCodes(codes)

  const codesRef = ref<string[]>([...access.codes])
  const off = access.onLifecycle((event) => {
    if (event === 'update') {
      codesRef.value = [...access.codes]
    }
  })
  onScopeDispose(off)

  return {
    access,
    codes: codesRef,
    setCodes: (next) => access.setCodes(next),
    has: (code) => access.has(code),
    hasAny: (list) => access.hasAny(list),
    hasAll: (list) => access.hasAll(list),
    canAccess: (code) => (code === undefined ? true : access.has(code)),
  }
}
