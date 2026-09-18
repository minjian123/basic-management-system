/**
 * 模态壳投影：把核心模态组件基类 `BaseModalShell` 投影为组合式（响应式显隐 + 关闭拦截）。
 */

import { BaseModalShell } from '@bms/core'
import { ref, type Ref } from 'vue'

/** 具体模态壳（可实例化）。 */
class ModalShell extends BaseModalShell {}

/** `useModalShell` 返回面。 */
export interface UseModalShellResult {
  /** 核心模态壳实例。 */
  shell: BaseModalShell
  /** 显隐（响应式）。 */
  visible: Ref<boolean>
  /** 打开。 */
  open: () => void
  /** 直接关闭（不经拦截）。 */
  close: (reason?: string) => void
  /** 请求关闭（经拦截；被拦截返回 `false`）。 */
  requestClose: (reason?: string) => boolean
  /** 设置关闭拦截器。 */
  setBeforeClose: (guard: (() => boolean) | undefined) => void
}

/**
 * 使用模态壳投影。
 *
 * @returns 模态壳实例与响应式面。
 */
export function useModalShell(): UseModalShellResult {
  const shell = new ModalShell()
  const visible = ref(shell.open)
  shell.onToggle((open) => {
    visible.value = open
  })
  return {
    shell,
    visible,
    open: () => shell.show(),
    close: (reason = 'close') => shell.hide(reason),
    requestClose: (reason = 'close') => shell.requestClose(reason),
    setBeforeClose: (guard) => {
      shell.beforeClose = guard
    },
  }
}
