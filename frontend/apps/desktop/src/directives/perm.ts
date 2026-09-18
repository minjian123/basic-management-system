/** 权限指令：`v-perm`（默认任一 / `.all` 全部 / `.not` 取反）；无权限移除 DOM。 */

import { evaluatePermission, type PermissionMode } from '@bms/core'
import type { Directive, DirectiveBinding } from 'vue'

import { getPermissionCodes } from '@/utils/perm'

const placeholders = new WeakMap<HTMLElement, Comment>()

/** 解析绑定值。 */
function resolve(binding: DirectiveBinding<string | string[]>): { required: string[]; mode: PermissionMode } {
  const value = binding.value
  const required = Array.isArray(value) ? value : [value]
  const mode = (binding.arg as PermissionMode | undefined) ?? 'any'
  return { required, mode }
}

/** 移除元素（注释锚点占位，便于恢复）。 */
function remove(el: HTMLElement): void {
  if (placeholders.has(el) || el.parentNode === null) {
    return
  }
  const anchor = document.createComment('v-perm')
  el.parentNode.replaceChild(anchor, el)
  placeholders.set(el, anchor)
}

/** 恢复元素到锚点位置。 */
function restore(el: HTMLElement): void {
  const anchor = placeholders.get(el)
  if (anchor === undefined) {
    return
  }
  anchor.parentNode?.replaceChild(el, anchor)
  placeholders.delete(el)
}

/** 应用权限判定。 */
function apply(el: HTMLElement, binding: DirectiveBinding<string | string[]>): void {
  const { required, mode } = resolve(binding)
  if (evaluatePermission(getPermissionCodes(), required, mode)) {
    restore(el)
  } else {
    remove(el)
  }
}

/** 权限指令。 */
export const vPerm: Directive<HTMLElement, string | string[]> = {
  mounted: apply,
  updated: apply,
}
