/**
 * `v-perm` 指令：按动作权限码（`业务:动作`）控制元素渲染。
 *
 * - 无权限**移除 DOM**（非 `display:none`）；移除时插入注释锚点，权限恢复后原位回插；
 * - 写法：string / string[]（默认任一满足 anyOf）、`.all`（全部满足）、`.not`（取反）；
 * - 求值时机：`mounted` / `updated`；判定经 `@bms/ui-vant` 注入点（`checkPerm`）；
 *   并监听权限版本（`usePermissionStore.permVersion`）变化重评。
 *
 * 前端显隐不构成安全边界，后端 `require_permission` 强校验为准。
 */

import { effectScope, watch, type Directive, type DirectiveBinding, type EffectScope } from 'vue'

import { checkPerm } from '@bms/ui-vant'

import { usePermissionStore } from '@/stores/permission'

interface PermState {
  binding: DirectiveBinding<string | string[]>
  scope?: EffectScope
  anchor?: Comment
  removed: boolean
}

const states = new WeakMap<HTMLElement, PermState>()

/** 归一权限码（空值 / 空串 / 空数组视为不限制） */
function codesOf(value: string | string[] | undefined): string[] {
  if (value === undefined || value === null) {
    return []
  }
  const list = Array.isArray(value) ? value : [value]
  return list.filter((code) => typeof code === 'string' && code.length > 0)
}

/** 判定是否放行 */
function allows(binding: DirectiveBinding<string | string[]>): boolean {
  const codes = codesOf(binding.value)
  if (codes.length === 0) {
    return true
  }
  // 判定经 ui-vant 注入点（宿主装配接权限 store；`any` / `all` 语义一致）
  const matched = checkPerm(codes, binding.modifiers.all === true ? 'all' : 'any')
  return binding.modifiers.not === true ? !matched : matched
}

/** 求值并同步 DOM（移除 / 锚点回插） */
function evaluate(el: HTMLElement, state: PermState): void {
  if (allows(state.binding)) {
    if (state.removed && state.anchor?.parentNode) {
      state.anchor.parentNode.insertBefore(el, state.anchor)
      state.removed = false
    }
    return
  }
  const parent = el.parentNode
  if (!state.removed && parent) {
    const anchor = document.createComment('v-perm')
    parent.insertBefore(anchor, el)
    parent.removeChild(el)
    state.anchor = anchor
    state.removed = true
  }
}

export const vPerm: Directive<HTMLElement, string | string[]> = {
  mounted(el, binding) {
    const state: PermState = { binding, removed: false }
    states.set(el, state)
    evaluate(el, state)
    const scope = effectScope(true)
    scope.run(() => {
      watch(
        () => usePermissionStore().permVersion,
        () => {
          evaluate(el, state)
        },
        { flush: 'post' },
      )
    })
    state.scope = scope
  },

  updated(el, binding) {
    const state = states.get(el)
    if (!state) {
      return
    }
    state.binding = binding
    evaluate(el, state)
  },

  unmounted(el) {
    const state = states.get(el)
    state?.scope?.stop()
    if (state?.anchor?.parentNode) {
      state.anchor.parentNode.removeChild(state.anchor)
    }
    states.delete(el)
  },
}

export default vPerm
