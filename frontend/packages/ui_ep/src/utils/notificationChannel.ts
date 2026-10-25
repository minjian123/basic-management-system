/** 通知多标签同步工具（`BroadcastChannel` 单一落点；能力缺失静默降级）。 */

/** 多标签同步消息。 */
export interface NotificationChannelMessage {
  /** 未读数（动作后校准值）。 */
  unreadCount?: number
  /** 最近消息 id。 */
  latestId?: string
  /** 动作类型。 */
  action?: 'read' | 'read-all' | 'remove' | 'incoming'
  /** 涉及的消息 id。 */
  ids?: string[]
}

/** 多标签同步通道。 */
export interface NotificationChannelHandle {
  /** 广播消息。 */
  publish(message: NotificationChannelMessage): void
  /** 关闭通道（幂等）。 */
  close(): void
}

/**
 * 创建多标签同步通道（无 `BroadcastChannel` 能力时回落空实现）。
 *
 * @param name 通道名。
 * @param handler 收到远端消息的回调。
 * @returns 通道句柄。
 */
export function createNotificationChannel(
  name: string,
  handler: (message: NotificationChannelMessage) => void,
): NotificationChannelHandle {
  if (typeof BroadcastChannel === 'undefined') {
    return { publish: () => {}, close: () => {} }
  }
  const channel = new BroadcastChannel(name)
  channel.onmessage = (event: MessageEvent<NotificationChannelMessage>) => {
    if (event.data !== null && typeof event.data === 'object') {
      handler(event.data)
    }
  }
  return {
    publish: (message) => {
      channel.postMessage(message)
    },
    close: () => {
      channel.close()
    },
  }
}
