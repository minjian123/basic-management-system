/**
 * 折叠面板上下文（`Collapse` 向 `CollapseItem` 下发的展开态与懒渲染）。
 */

import type { ComputedRef, InjectionKey } from 'vue'

export interface CollapseState {
  /** 已展开项（数组归一） */
  active: ComputedRef<string[]>
  /** 懒渲染（首次展开才挂载内容） */
  lazy: ComputedRef<boolean>
}

export const COLLAPSE_STATE_KEY: InjectionKey<CollapseState> = Symbol('bms:collapse-state')
