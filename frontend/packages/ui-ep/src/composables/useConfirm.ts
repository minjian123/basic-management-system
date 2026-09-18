/** 通用二次确认组合式：`confirm()` 返回 Promise，由挂载的 `ConfirmDialog` 结算。 */

import { ref, type Ref } from 'vue'

/** 确认选项。 */
export interface ConfirmOptions {
  /** 标题。 */
  title?: string
  /** 内容。 */
  content?: string
  /** 危险操作样式。 */
  danger?: boolean
  /** 确认按钮文案。 */
  confirmText?: string
  /** 取消按钮文案。 */
  cancelText?: string
}

/** 确认状态（绑定到 `ConfirmDialog`）。 */
export interface ConfirmState {
  /** 显隐。 */
  visible: Ref<boolean>
  /** 标题。 */
  title: Ref<string>
  /** 内容。 */
  content: Ref<string>
  /** 危险操作样式。 */
  danger: Ref<boolean>
  /** 确认按钮文案。 */
  confirmText: Ref<string>
  /** 取消按钮文案。 */
  cancelText: Ref<string>
}

const state: ConfirmState = {
  visible: ref(false),
  title: ref('确认'),
  content: ref(''),
  danger: ref(false),
  confirmText: ref('确定'),
  cancelText: ref('取消'),
}

let resolver: ((value: boolean) => void) | undefined

/**
 * 使用通用二次确认。
 *
 * @returns 状态与 `confirm` / `resolveConfirm`（后者由 `ConfirmDialog` 事件调用）。
 */
export function useConfirm(): {
  state: ConfirmState
  confirm: (options?: ConfirmOptions) => Promise<boolean>
  resolveConfirm: (value: boolean) => void
} {
  async function confirm(options: ConfirmOptions = {}): Promise<boolean> {
    state.title.value = options.title ?? '确认'
    state.content.value = options.content ?? ''
    state.danger.value = options.danger ?? false
    state.confirmText.value = options.confirmText ?? '确定'
    state.cancelText.value = options.cancelText ?? '取消'
    state.visible.value = true
    return new Promise<boolean>((resolve) => {
      resolver = resolve
    })
  }

  function resolveConfirm(value: boolean): void {
    state.visible.value = false
    resolver?.(value)
    resolver = undefined
  }

  return { state, confirm, resolveConfirm }
}
