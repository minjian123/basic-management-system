/** 通知组件基类投影：把核心 `BaseNotification` 投影为组合式（编排 / 角标 / 乐观已读删除 / 实时与轮询 / 多标签同步）。 */

import {
  BaseNotification,
  type NotificationConnectionState,
  type NotificationJobs,
  type NotificationMessage,
  type NotificationMessageType,
  type NotificationPhase,
  type NotificationReadFilter,
  type NotificationRealtimeAdapter,
  type NotificationRealtimePayload,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

import { createNotificationChannel } from '../utils/notificationChannel'
import { onVisibilityChange } from '../utils/notificationRealtime'

/** 具体通知件（可实例化）。 */
class NotificationState extends BaseNotification {}

/** 投影选项。 */
export interface UseBaseNotificationOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 页长。 */
  pageSize?: number
  /** 类型筛选。 */
  typeFilter?: NotificationMessageType | 'all'
  /** 已读筛选。 */
  readFilter?: NotificationReadFilter
  /** 初始消息清单。 */
  items?: NotificationMessage[]
  /** 初始未读数。 */
  unreadCount?: number
  /** 取数处理函数（未注入即占位零请求）。 */
  jobs?: NotificationJobs
  /** 实时适配器（未注入即轮询占位）。 */
  realtime?: NotificationRealtimeAdapter
  /** 多标签同步通道名（缺省 `bms:notification`）。 */
  channelName?: string
}

/** `useBaseNotification` 返回面。 */
export interface UseBaseNotificationResult {
  /** 通知基类实例。 */
  center: BaseNotification
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 编排阶段（响应式）。 */
  phase: Ref<NotificationPhase>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 消息清单（响应式）。 */
  items: Ref<NotificationMessage[]>
  /** 总数（响应式）。 */
  total: Ref<number>
  /** 页码（响应式）。 */
  page: Ref<number>
  /** 页长（响应式）。 */
  pageSize: Ref<number>
  /** 类型筛选（响应式）。 */
  typeFilter: Ref<NotificationMessageType | 'all'>
  /** 已读筛选（响应式）。 */
  readFilter: Ref<NotificationReadFilter>
  /** 未读数（响应式）。 */
  unreadCount: Ref<number>
  /** 角标计数（响应式）。 */
  badgeCount: Ref<number>
  /** 角标文案（响应式）。 */
  badgeText: Ref<string>
  /** 是否显示角标（响应式）。 */
  showBadge: Ref<boolean>
  /** 实时连接状态（响应式）。 */
  connectionState: Ref<NotificationConnectionState>
  /** 勾选集合（响应式）。 */
  selectedIds: Ref<string[]>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入取数处理函数。 */
  setJobs: (jobs: NotificationJobs) => void
  /** 注入 / 移除实时适配器。 */
  setRealtime: (adapter: NotificationRealtimeAdapter | undefined) => void
  /** 设置页码。 */
  setPage: (page: number) => void
  /** 设置页长。 */
  setPageSize: (size: number) => void
  /** 设置类型筛选。 */
  setTypeFilter: (type: NotificationMessageType | 'all') => void
  /** 设置已读筛选。 */
  setReadFilter: (read: NotificationReadFilter) => void
  /** 直接设置未读数（本地校准 / 多标签同步）。 */
  setUnreadCount: (value: number) => void
  /** 覆盖消息清单（种子 / 外部驱动）。 */
  setItems: (items: readonly NotificationMessage[]) => void
  /** 设置页面可见性（轮询门控）。 */
  setVisible: (visible: boolean) => void
  /** 取最近 N 条。 */
  recent: (limit?: number) => NotificationMessage[]
  /** 列表取数。 */
  load: () => Promise<NotificationMessage[] | undefined>
  /** 刷新。 */
  refresh: () => Promise<NotificationMessage[] | undefined>
  /** 未读数校准。 */
  syncUnread: () => Promise<number | undefined>
  /** 详情取数。 */
  loadDetail: (id: string) => Promise<NotificationMessage | undefined>
  /** 单条已读。 */
  markRead: (id: string) => Promise<boolean>
  /** 批量已读。 */
  readBatch: (ids: readonly string[]) => Promise<boolean>
  /** 全部已读。 */
  markAllRead: () => Promise<boolean>
  /** 单条删除。 */
  remove: (id: string) => Promise<boolean>
  /** 切换勾选。 */
  toggleSelect: (id: string) => void
  /** 清空勾选。 */
  clearSelection: () => void
  /** 接收实时增量。 */
  applyRealtime: (payload: NotificationRealtimePayload) => void
  /** 断线补偿。 */
  compensate: () => Promise<number | undefined>
  /** 建立实时连接。 */
  connect: () => void
  /** 断开实时连接。 */
  disconnect: () => void
}

/**
 * 使用通知组件基类投影。
 *
 * @param options 选项。
 * @returns 通知基类实例与响应式面。
 */
export function useBaseNotification(options: UseBaseNotificationOptions = {}): UseBaseNotificationResult {
  const center = new NotificationState()
  if (options.items !== undefined) {
    center.setItems(options.items)
  }
  if (options.pageSize !== undefined) {
    center.setPageSize(options.pageSize)
  }
  if (options.typeFilter !== undefined) {
    center.setTypeFilter(options.typeFilter)
  }
  if (options.readFilter !== undefined) {
    center.setReadFilter(options.readFilter)
  }
  if (options.unreadCount !== undefined) {
    center.setUnreadCount(options.unreadCount)
  }
  if (options.jobs !== undefined) {
    center.setJobs(options.jobs)
  }
  if (options.realtime !== undefined) {
    center.setRealtime(markRaw(toRaw(options.realtime)))
  }
  center.setReady(options.ready ?? false)

  const ready = ref(center.ready)
  const degraded = ref(center.degraded)
  const phase = ref<NotificationPhase>(center.phase)
  const errorMessage = ref(center.errorMessage)
  const items = ref<NotificationMessage[]>([...center.items])
  const total = ref(center.total)
  const page = ref(center.page)
  const pageSize = ref(center.pageSize)
  const typeFilter = ref<NotificationMessageType | 'all'>(center.typeFilter)
  const readFilter = ref<NotificationReadFilter>(center.readFilter)
  const unreadCount = ref(center.unreadCount)
  const badgeCount = ref(center.badgeCount)
  const badgeText = ref(center.badgeText)
  const showBadge = ref(center.showBadge)
  const connectionState = ref<NotificationConnectionState>(center.connectionState)
  const selectedIds = ref<string[]>([...center.selectedIds])

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = center.ready
    degraded.value = center.degraded
    phase.value = center.phase
    errorMessage.value = center.errorMessage
    items.value = [...center.items]
    total.value = center.total
    page.value = center.page
    pageSize.value = center.pageSize
    typeFilter.value = center.typeFilter
    readFilter.value = center.readFilter
    unreadCount.value = center.unreadCount
    badgeCount.value = center.badgeCount
    badgeText.value = center.badgeText
    showBadge.value = center.showBadge
    connectionState.value = center.connectionState
    selectedIds.value = [...center.selectedIds]
  }

  const channel =
    typeof options.channelName === 'string'
      ? createNotificationChannel(options.channelName, (message) => {
          if (message.unreadCount !== undefined) {
            center.setUnreadCount(message.unreadCount)
          }
          sync()
        })
      : undefined

  const offVisibility = onVisibilityChange((visible) => {
    center.setVisible(visible)
  })

  const off = center.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    offVisibility()
    channel?.close()
    center.dispose()
  })

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

  /** 广播角标（多标签同步）。 */
  const publishBadge = (action: 'read' | 'read-all' | 'remove' | 'incoming', ids?: string[]): void => {
    channel?.publish({
      unreadCount: center.unreadCount,
      latestId: center.items[0]?.id,
      action,
      ids,
    })
  }

  return {
    center,
    ready,
    degraded,
    phase,
    errorMessage,
    items,
    total,
    page,
    pageSize,
    typeFilter,
    readFilter,
    unreadCount,
    badgeCount,
    badgeText,
    showBadge,
    connectionState,
    selectedIds,
    setReady: (value) => run(() => center.setReady(value)),
    setJobs: (jobs) => run(() => center.setJobs(jobs)),
    setRealtime: (adapter) => run(() => center.setRealtime(adapter === undefined ? undefined : markRaw(toRaw(adapter)))),
    setPage: (value) => run(() => center.setPage(value)),
    setPageSize: (size) => run(() => center.setPageSize(size)),
    setTypeFilter: (type) => run(() => center.setTypeFilter(type)),
    setReadFilter: (read) => run(() => center.setReadFilter(read)),
    setUnreadCount: (value) => run(() => center.setUnreadCount(value)),
    setItems: (value) => run(() => center.setItems(value)),
    setVisible: (visible) => center.setVisible(visible),
    recent: (limit) => center.recent(limit),
    load: async () => {
      const value = await center.load()
      sync()
      return value
    },
    refresh: async () => {
      const value = await center.refresh()
      sync()
      return value
    },
    syncUnread: async () => {
      const value = await center.syncUnread()
      sync()
      return value
    },
    loadDetail: async (id) => {
      const value = await center.loadDetail(id)
      sync()
      return value
    },
    markRead: async (id) => {
      const value = await center.markRead(id)
      sync()
      publishBadge('read', [id])
      return value
    },
    readBatch: async (ids) => {
      const value = await center.readBatch(ids)
      sync()
      publishBadge('read', [...ids])
      return value
    },
    markAllRead: async () => {
      const value = await center.markAllRead()
      sync()
      publishBadge('read-all')
      return value
    },
    remove: async (id) => {
      const value = await center.remove(id)
      sync()
      publishBadge('remove', [id])
      return value
    },
    toggleSelect: (id) => run(() => center.toggleSelect(id)),
    clearSelection: () => run(() => center.clearSelection()),
    applyRealtime: (payload) => {
      center.applyRealtime(payload)
      sync()
    },
    compensate: async () => {
      const value = await center.compensate()
      sync()
      return value
    },
    connect: () => run(() => center.connect()),
    disconnect: () => run(() => center.disconnect()),
  }
}
