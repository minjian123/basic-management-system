/**
 * 通知组件基类（通知族）：站内信 / 公告的展示与已读状态。
 */

import { BaseNotice } from './notice'

/** 通知项。 */
export interface NotificationItem {
  /** 唯一标识。 */
  id: string
  /** 标题。 */
  title: string
  /** 是否已读。 */
  read: boolean
}

/** 通知组件基类（抽象）。 */
export abstract class BaseNotification extends BaseNotice {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'notification'
  /** 通知列表。 */
  readonly items: NotificationItem[] = []

  /** 未读数。 */
  get unread(): number {
    return this.items.filter((item) => !item.read).length
  }

  /**
   * 追加通知（置顶）。
   *
   * @param item 通知项。
   */
  push(item: NotificationItem): void {
    this.items.unshift({ ...item })
    this.notifyLifecycle('update')
  }

  /**
   * 标记单条已读。
   *
   * @param id 通知标识。
   */
  markRead(id: string): void {
    const item = this.items.find((entry) => entry.id === id)
    if (item !== undefined) {
      item.read = true
      this.notifyLifecycle('update')
    }
  }

  /** 全部标记已读。 */
  markAllRead(): void {
    for (const item of this.items) {
      item.read = true
    }
    this.notifyLifecycle('update')
  }
}
