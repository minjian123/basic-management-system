/** 表单页投影：把核心表单页组合能力基类 `BaseFormPage` 投影为组合式（三态 / 脏数据 / 提交）。 */

import { BaseFormPage, type FormMode } from '@bms/core'

export type { FormMode }
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体表单页（可实例化）。 */
class FormPageState extends BaseFormPage {}

/** 选项。 */
export interface UseBaseFormPageOptions {
  /** 初始模式。 */
  mode?: FormMode
  /** 提交器。 */
  submitter?: () => Promise<void>
}

/** `useBaseFormPage` 返回面。 */
export interface UseBaseFormPageResult {
  /** 表单页基类实例。 */
  page: BaseFormPage
  /** 模式（响应式）。 */
  mode: Ref<FormMode>
  /** 脏数据（响应式）。 */
  dirty: Ref<boolean>
  /** 设置模式。 */
  setMode: (mode: FormMode) => void
  /** 标记脏数据。 */
  markDirty: (dirty?: boolean) => void
  /** 提交（成功后清脏）。 */
  submit: () => Promise<void>
  /** 返回是否需要确认（脏数据）。 */
  shouldConfirmBack: () => boolean
}

/**
 * 使用表单页投影。
 *
 * @param options 选项。
 * @returns 表单页基类实例与响应式面。
 */
export function useBaseFormPage(options: UseBaseFormPageOptions = {}): UseBaseFormPageResult {
  const page = new FormPageState()
  if (options.mode !== undefined) {
    page.mode = options.mode
  }
  if (options.submitter !== undefined) {
    page.submitter = options.submitter
  }

  const mode = ref<FormMode>(page.mode)
  const dirty = ref(page.dirty)
  const off = page.onLifecycle((event) => {
    if (event === 'update') {
      mode.value = page.mode
      dirty.value = page.dirty
    }
  })
  onScopeDispose(off)

  return {
    page,
    mode,
    dirty,
    setMode: (next) => {
      page.setMode(next)
      page.notifyLifecycle('update')
    },
    markDirty: (next = true) => {
      page.markDirty(next)
      page.notifyLifecycle('update')
    },
    submit: async () => {
      await page.submit()
      page.notifyLifecycle('update')
    },
    shouldConfirmBack: () => page.back(),
  }
}
