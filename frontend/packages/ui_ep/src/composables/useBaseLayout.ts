/** 布局件投影：把核心布局组件基类 `BaseLayout` 投影为组合式（栅格列数 / 间距 / 显隐）。 */

import { BaseLayout } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体布局件（可实例化）。 */
class LayoutState extends BaseLayout {}

/** 选项。 */
export interface UseBaseLayoutOptions {
  /** 栅格总列数。 */
  columns?: number
  /** 间距（像素 / 令牌键）。 */
  gap?: number | string
}

/** `useBaseLayout` 返回面。 */
export interface UseBaseLayoutResult {
  /** 布局基类实例。 */
  layout: BaseLayout
  /** 栅格列数（响应式）。 */
  columns: Ref<number>
  /** 间距（响应式）。 */
  gap: Ref<number | string>
  /** 是否隐藏（响应式）。 */
  hidden: Ref<boolean>
  /** 设置列数。 */
  setColumns: (columns: number) => void
  /** 设置间距。 */
  setGap: (gap: number | string) => void
  /** 设置显隐。 */
  setHidden: (hidden: boolean) => void
}

/**
 * 使用布局件投影。
 *
 * @param options 选项。
 * @returns 布局基类实例与响应式面。
 */
export function useBaseLayout(options: UseBaseLayoutOptions = {}): UseBaseLayoutResult {
  const layout = new LayoutState()
  if (options.columns !== undefined) {
    layout.columns = options.columns
  }
  if (options.gap !== undefined) {
    layout.gap = options.gap
  }

  const columns = ref(layout.columns)
  const gap = ref(layout.gap)
  const hidden = ref(layout.hidden)
  const off = layout.onLifecycle((event) => {
    if (event === 'update') {
      columns.value = layout.columns
      gap.value = layout.gap
      hidden.value = layout.hidden
    }
  })
  onScopeDispose(off)

  return {
    layout,
    columns,
    gap,
    hidden,
    setColumns: (next) => {
      layout.columns = next
      layout.notifyLifecycle('update')
    },
    setGap: (next) => {
      layout.gap = next
      layout.notifyLifecycle('update')
    },
    setHidden: (next) => layout.setHidden(next),
  }
}
