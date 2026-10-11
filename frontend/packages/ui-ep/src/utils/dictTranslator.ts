/** 字典标签翻译器：供 `DataTable` / `DescriptionList` 的 `translator` 注入（未加载先显示原值、加载后刷新）。 */

import { DICT_JOIN, type BaseDictStore } from '@bms/core'

/**
 * 创建字典标签翻译器（统一走缓存与批量翻译；未命中触发一次子集回填、不阻塞渲染）。
 *
 * @param store 字典缓存能力实例。
 * @returns 翻译函数（`(dataSourceKey, value) => label | undefined`；未就绪 / 未命中返回 `undefined` 由宿主显示原值）。
 */
export function createDictTranslator(store: BaseDictStore): (dataSourceKey: string, value: unknown) => string | undefined {
  return (dataSourceKey: string, value: unknown): string | undefined => {
    if (dataSourceKey === '' || value === undefined || value === null) {
      return undefined
    }
    if (Array.isArray(value)) {
      const values = value.map((entry) => String(entry))
      const labels = values.map((entry) => store.labelOf(dataSourceKey, entry))
      if (labels.some((label) => label === undefined)) {
        void store.resolveValues(dataSourceKey, values)
        return undefined
      }
      return (labels as string[]).join(DICT_JOIN)
    }
    const text = String(value)
    const label = store.labelOf(dataSourceKey, text)
    if (label === undefined) {
      void store.resolveValues(dataSourceKey, [text])
      return undefined
    }
    return label
  }
}
