/** 模块边界错误态：模块加载 / 渲染失败时由边界组件渲染兜底（复用 `03_02` 错误页）。 */

import { ref, type Ref } from 'vue'

/** 模块错误态。 */
export interface ModuleErrorState {
  /** 模块名。 */
  module: string
  /** 模块版本。 */
  version: string
  /** 失败原因。 */
  reason: string
}

const state = ref<ModuleErrorState | null>(null)

/**
 * 记录模块错误。
 *
 * @param error 错误态。
 */
export function setModuleError(error: ModuleErrorState): void {
  state.value = error
}

/** 清除模块错误（重试前调用）。 */
export function clearModuleError(): void {
  state.value = null
}

/** 模块错误态（响应式）。 */
export function useModuleError(): Ref<ModuleErrorState | null> {
  return state
}
