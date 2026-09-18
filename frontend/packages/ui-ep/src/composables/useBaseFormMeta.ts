/** 表单元数据投影：把核心表单元数据能力基类 `BaseFormMeta` 投影为组合式（加载 / 版本比对）。 */

import { BaseFormMeta } from '@bms/core'
import { onScopeDispose, ref, shallowRef, type Ref } from 'vue'

/** 具体表单元数据件（可实例化）。 */
class FormMetaState extends BaseFormMeta {}

/** 选项。 */
export interface UseBaseFormMetaOptions {
  /** 元数据加载器（未注入则占位不请求）。 */
  loader?: () => Promise<unknown>
}

/** `useBaseFormMeta` 返回面。 */
export interface UseBaseFormMetaResult {
  /** 表单元数据基类实例。 */
  formMeta: BaseFormMeta
  /** 元数据（响应式）。 */
  meta: Ref<unknown>
  /** 元数据版本（响应式）。 */
  dataVersion: Ref<number>
  /** 加载元数据（未注入加载器则占位不动作）。 */
  load: () => Promise<void>
  /** 依据远端版本判断是否需要刷新。 */
  needsRefresh: (version: number) => boolean
}

/**
 * 使用表单元数据投影。
 *
 * @param options 选项。
 * @returns 表单元数据基类实例与响应式面。
 */
export function useBaseFormMeta(options: UseBaseFormMetaOptions = {}): UseBaseFormMetaResult {
  const formMeta = new FormMetaState()
  if (options.loader !== undefined) {
    formMeta.loader = options.loader
  }

  const meta = shallowRef<unknown>(formMeta.meta)
  const dataVersion = ref(formMeta.dataVersion)
  const sync = (): void => {
    meta.value = formMeta.meta
    dataVersion.value = formMeta.dataVersion
  }
  const off = formMeta.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    formMeta,
    meta,
    dataVersion,
    load: async () => {
      await formMeta.load()
      sync()
    },
    needsRefresh: (version) => formMeta.needsRefresh(version),
  }
}
