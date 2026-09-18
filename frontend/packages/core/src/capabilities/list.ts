/**
 * 列表组件基类：列表数据 / 滚动加载 / 空态与错误态 / 刷新。
 */

import { BaseDataState } from './data-state'

/** 列表组件基类（抽象）。 */
export abstract class BaseList extends BaseDataState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'list'
  /** 列表项。 */
  items: unknown[] = []
  /** 是否已加载完（触底不再加载）。 */
  finished = false

  /**
   * 设置列表项（整体替换）。
   *
   * @param items 列表项。
   */
  setItems(items: readonly unknown[]): void {
    this.items = [...items]
  }

  /**
   * 追加列表项（滚动加载）。
   *
   * @param items 追加项。
   */
  append(items: readonly unknown[]): void {
    this.items.push(...items)
  }

  /** 刷新（清空 + 重新加载占位）。 */
  refresh(): void {
    this.items = []
    this.finished = false
    this.begin()
  }
}
