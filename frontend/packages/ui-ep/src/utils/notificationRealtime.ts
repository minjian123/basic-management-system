/** 通知轮询占位与页面可见性工具（浏览器 API 单一落点；核心与投影判定逻辑不触 DOM）。 */

import { NOTIFICATION_POLL_INTERVAL } from '@bms/core'

/** 轮询占位选项。 */
export interface UnreadPollingOptions {
  /** 轮询间隔（毫秒；缺省 `NOTIFICATION_POLL_INTERVAL`）。 */
  intervalMs?: number
  /** 页面是否可见。 */
  visible: () => boolean
  /** 取未读数（校准）。 */
  loadUnread: () => Promise<unknown>
}

/** 轮询占位句柄。 */
export interface UnreadPollingHandle {
  /** 停止轮询（幂等）。 */
  stop(): void
  /** 立即触发一次（可见恢复 / 聚焦）。 */
  kick(): void
}

/**
 * 启动未读数轮询占位（仅页面可见时触发；未注入实时适配器时使用）。
 *
 * @param options 选项。
 * @returns 启停句柄。
 */
export function startUnreadPolling(options: UnreadPollingOptions): UnreadPollingHandle {
  const interval = Math.max(1, options.intervalMs ?? NOTIFICATION_POLL_INTERVAL)
  const timer = setInterval(() => {
    if (options.visible()) {
      void options.loadUnread()
    }
  }, interval)
  return {
    stop: () => clearInterval(timer),
    kick: () => {
      if (options.visible()) {
        void options.loadUnread()
      }
    },
  }
}

/**
 * 订阅页面可见性变化（能力缺失降级为恒可见且不注册监听）。
 *
 * @param handler 可见性回调。
 * @returns 取消函数（幂等）。
 */
export function onVisibilityChange(handler: (visible: boolean) => void): () => void {
  if (typeof document === 'undefined' || typeof document.addEventListener !== 'function') {
    handler(true)
    return () => {}
  }
  const listener = (): void => handler(document.visibilityState !== 'hidden')
  document.addEventListener('visibilitychange', listener)
  return () => document.removeEventListener('visibilitychange', listener)
}
