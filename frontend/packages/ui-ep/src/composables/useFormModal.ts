/** 弹窗表单组合式：打开 / 关闭 / 提交 / 重置 / 加载态。 */

import { ref, type Ref } from 'vue'

/** 表单三态。 */
export type FormMode = 'create' | 'edit' | 'detail'

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
  const visible = ref(false)
  const mode = ref<FormMode>('create')
  const title = ref('')
  const dirty = ref(false)
  const loading = ref(false)

  function open(next: FormMode = 'create', nextTitle = ''): void {
    mode.value = next
    title.value = nextTitle
    dirty.value = false
    visible.value = true
  }

  function close(): void {
    visible.value = false
  }

  function reset(): void {
    dirty.value = false
  }

  function markDirty(value = true): void {
    dirty.value = value
  }

  async function submit(values?: T): Promise<void> {
    loading.value = true
    try {
      await options.submit?.(values as T)
      dirty.value = false
    } finally {
      loading.value = false
    }
  }

  return { visible, mode, title, dirty, loading, open, close, reset, markDirty, submit }
}
