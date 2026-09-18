/** 选项源投影：把核心选项源能力基类 `BaseOptionSource` 投影为组合式（加载 / 版本比对 / 搜索回显）。 */

import { BaseOptionSource, type OptionItem } from '@bms/core'
import { onScopeDispose, ref, shallowRef, type Ref } from 'vue'

/** 具体选项源（可实例化）。 */
class OptionSourceState<T> extends BaseOptionSource<T> {}

/** 选项。 */
export interface UseBaseOptionSourceOptions<T> {
  /** 选项加载器（未注入则占位不请求）。 */
  loader?: () => Promise<OptionItem<T>[]>
}

/** `useBaseOptionSource` 返回面。 */
export interface UseBaseOptionSourceResult<T = unknown> {
  /** 选项源基类实例。 */
  optionSource: BaseOptionSource<T>
  /** 已加载选项（响应式）。 */
  options: Ref<OptionItem<T>[]>
  /** 数据版本（响应式）。 */
  dataVersion: Ref<number>
  /** 加载选项（未注入加载器则占位不动作）。 */
  load: () => Promise<void>
  /** 按值回显文案。 */
  getLabel: (value: T) => string | undefined
  /** 按关键字搜索（空串返回全部）。 */
  search: (keyword: string) => OptionItem<T>[]
}

/**
 * 使用选项源投影。
 *
 * @param options 选项。
 * @returns 选项源基类实例与响应式面。
 */
export function useBaseOptionSource<T = unknown>(
  options: UseBaseOptionSourceOptions<T> = {},
): UseBaseOptionSourceResult<T> {
  const optionSource = new OptionSourceState<T>()
  if (options.loader !== undefined) {
    optionSource.loader = options.loader
  }

  const list = shallowRef<OptionItem<T>[]>([...optionSource.options])
  const dataVersion = ref(optionSource.dataVersion)
  const sync = (): void => {
    list.value = [...optionSource.options]
    dataVersion.value = optionSource.dataVersion
  }
  const off = optionSource.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    optionSource,
    options: list,
    dataVersion,
    load: async () => {
      await optionSource.load()
      sync()
    },
    getLabel: (value) => optionSource.getLabel(value),
    search: (keyword) => optionSource.search(keyword),
  }
}
