/** 富文本内核投影：把核心编辑器内核能力基类 `BaseEditorKernel` 投影为组合式（模式 / 只读）。 */

import { BaseEditorKernel, type EditorMode } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体编辑器内核（可实例化）。 */
class RichTextKernel extends BaseEditorKernel {}

/** 选项。 */
export interface UseRichTextKernelOptions {
  /** 初始模式（缺省 `rich`）。 */
  mode?: EditorMode
  /** 只读。 */
  readOnly?: boolean
}

/** `useRichTextKernel` 返回面。 */
export interface UseRichTextKernelResult {
  /** 内核基类实例。 */
  kernel: BaseEditorKernel
  /** 模式（响应式）。 */
  mode: Ref<EditorMode>
  /** 只读（响应式）。 */
  readOnly: Ref<boolean>
  /** 切换模式。 */
  setMode: (mode: EditorMode) => void
  /** 设置只读。 */
  setReadOnly: (readOnly: boolean) => void
}

/**
 * 使用富文本内核投影。
 *
 * @param options 选项。
 * @returns 内核基类实例与响应式面。
 */
export function useRichTextKernel(options: UseRichTextKernelOptions = {}): UseRichTextKernelResult {
  const kernel = new RichTextKernel()
  if (options.mode !== undefined) {
    kernel.mode = options.mode
  }

  const mode = ref<EditorMode>(kernel.mode)
  const readOnly = ref(options.readOnly ?? false)
  const off = kernel.onLifecycle((event) => {
    if (event === 'update') {
      mode.value = kernel.mode
    }
  })
  onScopeDispose(off)

  return {
    kernel,
    mode,
    readOnly,
    setMode: (next) => {
      kernel.mode = next
      kernel.notifyLifecycle('update')
    },
    setReadOnly: (next) => {
      readOnly.value = next
    },
  }
}
