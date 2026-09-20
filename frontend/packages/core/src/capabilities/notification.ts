/**
 * 通知组件基类（通知族）：站内信 / 公告的展示与已读状态，以及类型语义色 / 文案 / 跳转展示语义。
 *
 * 父基类由 `BaseNotice` 调整为 **通知中心编排能力基类 `BaseNotificationCenter`**
 * （中间层插入为兼容变更）；取数与实时编排由父类承担，具体件只做渲染与交互回传。
 */

import { countUnread, jumpTargetOf as resolveJumpTarget, messageTypeLabel, normalizeNotificationMessage, resolveMessageSemantic } from '../domain/notification'
import type { NotificationMessage, NotificationMessageType } from '../domain/notification'
import type { StatusSemantic } from '../domain/status'
import { BaseNotificationCenter } from './notification-center'

/** 通知项（冻结的最小形状；兼容 `NotificationMessage`）。 */
export interface NotificationItem {
  /** 唯一标识。 */
  id: string
  /** 标题。 */
  title: string
  /** 是否已读。 */
  read: boolean
}

/** 通知组件基类（抽象）。 */
export abstract class BaseNotification extends BaseNotificationCenter {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'notification'
  /** 依赖登记。 */
  override readonly depends: readonly string[] = ['notification-center']

  /** 未读数（基于消息清单本地计数）。 */
  get unread(): number {
    return countUnread(this.items)
  }

  /**
   * 追加通知（置顶）。
   *
   * @param item 通知项。
   */
  push(item: NotificationItem): void {
    const message = normalizeNotificationMessage(item)
    if (message === undefined) {
      return
    }
    this.items.unshift(message)
    this.notifyLifecycle('update')
  }

  /**
   * 消息类型语义色（复用 `domain/status.ts` 五档）。
   *
   * @param type 消息类型。
   * @returns 语义色。
   */
  messageSemantic(type?: NotificationMessageType): StatusSemantic {
    return resolveMessageSemantic(type)
  }

  /**
   * 消息类型中文标签。
   *
   * @param type 消息类型。
   * @returns 标签文案。
   */
  messageLabel(type?: NotificationMessageType): string {
    return messageTypeLabel(type)
  }

  /**
   * 跳转目标（无 `bizType` / `bizId` 返回 `undefined`）。
   *
   * @param message 消息。
   * @returns 跳转目标或 `undefined`。
   */
  jumpTargetOf(message: NotificationMessage): { bizType: string; bizId: string } | undefined {
    return resolveJumpTarget(message)
  }
}
