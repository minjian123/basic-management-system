/** 选中集合投影：把核心选中集合能力基类 `BaseSelection` 投影为组合式（选中键 / 计数 / 摘要 / 跨页全选）。 */

import { BaseSelection, type SelectionKey, type SelectionMode, type SelectionSummary } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体选中集合（可实例化）。 */
class Selection extends BaseSelection {}

/** 选项。 */
export interface UseBaseSelectionOptions {
  /** 选择模式（缺省仅当前页）。 */
  mode?: SelectionMode
  /** 当前查询总记录数。 */
  total?: number
  /** 当前页行键。 */
  pageKeys?: SelectionKey[]
  /** 初始选中集合。 */
  selected?: SelectionKey[]
}

/** `useBaseSelection` 返回面。 */
export interface UseBaseSelectionResult {
  /** 选中集合基类实例。 */
  selection: BaseSelection
  /** 选中键（响应式）。 */
  selected: Ref<SelectionKey[]>
  /** 已选数量（响应式）。 */
  count: Ref<number>
  /** 选中摘要（响应式）。 */
  summary: Ref<SelectionSummary>
  /** 是否无选中项（响应式）。 */
  isEmpty: Ref<boolean>
  /** 当前页是否全选（响应式）。 */
  isAllPageSelected: Ref<boolean>
  /** 当前页是否部分选中（响应式）。 */
  somePageSelected: Ref<boolean>
  /** 选择模式（响应式）。 */
  mode: Ref<SelectionMode>
  /** 当前页行键（响应式）。 */
  pageKeys: Ref<SelectionKey[]>
  /** 设置选择模式。 */
  setMode: (mode: SelectionMode) => void
  /** 设置总记录数。 */
  setTotal: (total: number) => void
  /** 设置当前页行键。 */
  setPageKeys: (keys: SelectionKey[]) => void
  /** 设置某键选中态。 */
  select: (key: SelectionKey, selected?: boolean) => void
  /** 切换某键选中态。 */
  toggle: (key: SelectionKey) => void
  /** 当前页全选。 */
  selectPage: () => void
  /** 当前页取消全选。 */
  deselectPage: () => void
  /** 当前页反选。 */
  invertPage: () => void
  /** 跨页全选。 */
  selectAllAcrossPages: () => void
  /** 清空选中集合。 */
  clear: () => void
  /** 整体回写选中集合（按内容比较）。 */
  replace: (keys: SelectionKey[]) => void
  /** 是否选中某键。 */
  isSelected: (key: SelectionKey) => boolean
}

/**
 * 使用选中集合投影。
 *
 * @param options 选项。
 * @returns 选中集合基类实例与响应式面。
 */
export function useBaseSelection(options: UseBaseSelectionOptions = {}): UseBaseSelectionResult {
  const selection = new Selection()
  if (options.mode !== undefined) {
    selection.setMode(options.mode)
  }
  if (options.total !== undefined) {
    selection.setTotal(options.total)
  }
  if (options.pageKeys !== undefined) {
    selection.setPageKeys(options.pageKeys)
  }
  if (options.selected !== undefined) {
    selection.replace(options.selected)
  }

  const selected = ref<SelectionKey[]>([...selection.selected])
  const count = ref(selection.count)
  const summary = ref(selection.summary)
  const isEmpty = ref(selection.isEmpty)
  const isAllPageSelected = ref(selection.isAllPageSelected)
  const somePageSelected = ref(selection.somePageSelected)
  const mode = ref<SelectionMode>(selection.mode)
  const pageKeys = ref<SelectionKey[]>([...selection.pageKeys])

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    selected.value = [...selection.selected]
    count.value = selection.count
    summary.value = selection.summary
    isEmpty.value = selection.isEmpty
    isAllPageSelected.value = selection.isAllPageSelected
    somePageSelected.value = selection.somePageSelected
    mode.value = selection.mode
    pageKeys.value = [...selection.pageKeys]
  }

  const off = selection.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    selection,
    selected,
    count,
    summary,
    isEmpty,
    isAllPageSelected,
    somePageSelected,
    mode,
    pageKeys,
    setMode: (next) => {
      selection.setMode(next)
      sync()
    },
    setTotal: (total) => {
      selection.setTotal(total)
      sync()
    },
    setPageKeys: (keys) => {
      selection.setPageKeys(keys)
      sync()
    },
    select: (key, isSelected) => {
      selection.select(key, isSelected)
      sync()
    },
    toggle: (key) => {
      selection.toggle(key)
      sync()
    },
    selectPage: () => {
      selection.selectPage()
      sync()
    },
    deselectPage: () => {
      selection.deselectPage()
      sync()
    },
    invertPage: () => {
      selection.invertPage()
      sync()
    },
    selectAllAcrossPages: () => {
      selection.selectAllAcrossPages()
      sync()
    },
    clear: () => {
      selection.clear()
      sync()
    },
    replace: (keys) => {
      selection.replace(keys)
      sync()
    },
    isSelected: (key) => selection.isSelected(key),
  }
}
