/** 拖拽基座能力：拖拽中 / 悬停 / 顺序状态骨架（渲染层负责指针事件，核心只维护状态）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface DragDropOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
}

export class BaseDragDrop extends BaseCapability {
  readonly dragging = observable<string>('')
  readonly overKey = observable<string>('')

  constructor(options: DragDropOptions = {}) {
    super({ ...options, key: options.key ?? 'drag-drop' })
  }

  start(key: string): void {
    this.dragging.set(key)
  }

  over(key: string): void {
    this.overKey.set(key)
  }

  end(): void {
    this.dragging.set('')
    this.overKey.set('')
  }

  /** 排序结果（把 from 移到 to 位置；越界原样返回） */
  reorder<T>(list: readonly T[], from: number, to: number): T[] {
    if (from < 0 || to < 0 || from >= list.length || to >= list.length || from === to) {
      return [...list]
    }
    const next = [...list]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved as T)
    return next
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), dragging: this.dragging.get() }
  }
}
