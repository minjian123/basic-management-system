/** 弹窗表单组合式：打开 / 关闭 / 提交 / 重置 / 加载态（状态经核心 `BaseFormPage` 与 `BaseModalShell` 投影）。 */

import { type FormMode } from '@bms/core'
import { ref, type Ref } from 'vue'

import { useBaseFormPage } from './useBaseFormPage'
import { useModalShell } from './useModalShell'

/** 选项。 */
export interface UseFormModalOptions<T> {
  /** 提交处理器（缺省仅切换加载态）。 */
  submit?: (values: T) => Promise<void> | void
}

/** `useFormModal` 返回面。 */
export interface UseFormModalResult<T> {
  /** 显隐。 */
  visible: Ref<boolean>
  /** 三态。 */
  mode: Ref<FormMode>
  /** 标题。 */
  title: Ref<string>
  /** 脏数据。 */
  dirty: Ref<boolean>
  /** 提交加载态。 */
  loading: Ref<boolean>
  /** 打开（可指定三态与标题）。 */
  open: (mode?: FormMode, title?: string) => void
  /** 关闭。 */
  close: () => void
  /** 重置脏数据。 */
  reset: () => void
  /** 标记脏数据。 */
  markDirty: (dirty?: boolean) => void
  /** 提交。 */
  submit: (values?: T) => Promise<void>
}

/**
 * 弹窗表单组合式。
 *
 * @param options 选项。
 */
export function useFormModal<T = unknown>(options: UseFormModalOptions<T> = {}): UseFormModalResult<T> {
  const shell = useModalShell()
  const title = ref('')
  const loading = ref(false)
  let pending: T | undefined

  const form = useBaseFormPage({
    submitter:
      options.submit === undefined
        ? undefined
        : async () => {
            await options.submit?.(pending as T)
          },
  })

  function open(mode: FormMode = 'create', nextTitle = ''): void {
    form.setMode(mode)
    form.markDirty(false)
    title.value = nextTitle
    shell.open()
  }

  function close(): void {
    shell.close('close')
  }

  async function submit(values?: T): Promise<void> {
    pending = values
    loading.value = true
    try {
      await form.submit()
      if (options.submit === undefined) {
        form.markDirty(false)
      }
    } finally {
      loading.value = false
    }
  }

  return {
    visible: shell.visible,
    mode: form.mode,
    title,
    dirty: form.dirty,
    loading,
    open,
    close,
    reset: () => form.markDirty(false),
    markDirty: (dirty = true) => form.markDirty(dirty),
    submit,
  }
}
