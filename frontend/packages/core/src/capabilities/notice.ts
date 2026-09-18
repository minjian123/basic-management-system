/**
 * 提示通知能力基类：类型 / 时长 / 关闭语义 / 队列。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 提示类型。 */
export type NoticeType = 'info' | 'success' | 'warning' | 'error'

/** 队列项。 */
export interface NoticeItem {
  /** 唯一标识。 */
  id: string
  /** 类型。 */
  type: NoticeType
  /** 内容。 */
  content: string
}

/** 通知能力基类（抽象）。 */
export abstract class BaseNotice extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'notice'
  /** 缺省类型。 */
  type: NoticeType = 'info'
  /** 自动关闭时长（毫秒；0 表示不自动关闭）。 */
  duration = 3000
  /** 是否可关闭。 */
  closable = true
  /** 当前队列。 */
  readonly queue: NoticeItem[] = []

  /**
   * 入队一条通知。
   *
   * @param content 内容。
   * @param type 类型（缺省用组件缺省类型）。
   * @returns 通知标识。
   */
  enqueue(content: string, type: NoticeType = this.type): string {
    const id = `${this.identifier}:${this.queue.length + 1}`
    this.queue.push({ id, type, content })
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
    return id
  }

  /**
   * 关闭通知（缺省清空队列）。
   *
   * @param id 指定通知标识；缺省关闭全部。
   */
  dismiss(id?: string): void {
    if (id === undefined) {
      this.queue.length = 0
    } else {
      const index = this.queue.findIndex((item) => item.id === id)
      if (index >= 0) {
        this.queue.splice(index, 1)
      }
    }
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
