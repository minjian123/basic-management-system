/**
 * 通知中心编排能力基类（通知族能力基类）：未读数与角标、列表 / 详情取数编排、实时订阅与断线补偿、
 * 批量 / 全部已读、单条删除、本地乐观 + 失败回滚、轮询占位。
 *
 * 父基类 `BaseNotice`；组件基类 `BaseNotification` 派生其下。取数与实时一经纪注入式处理函数 /
 * 适配器接入，**未注入即占位零请求**；核心不依赖 Vue / DOM / `socket.io-client`。
 */

import { BaseNotice } from './notice'
import {
  NOTIFICATION_BATCH_MAX,
  NOTIFICATION_PAGE_SIZE_DEFAULT,
  NOTIFICATION_PAGE_SIZE_MAX,
  NOTIFICATION_POLL_INTERVAL,
  applyIncoming,
  applyOptimisticRead,
  applyOptimisticReadAll,
  applyOptimisticRemove,
  badgeTextOf,
  buildNotificationParams,
  clampBadgeCount,
  isPollingNeeded,
  normalizeNotificationMessage,
  normalizeNotificationMessages,
  normalizeNotificationPage,
  parseUnreadCount,
  recentMessages,
  restoreSnapshot,
  shouldShowBadge,
  type NotificationConnectionState,
  type NotificationMessage,
  type NotificationMessageType,
  type NotificationQuery,
  type NotificationReadFilter,
  type NotificationRealtimePayload,
  type NotificationSnapshot,
} from '../domain/notification'

/** 通知取数与动作处理函数（使用方注入；未注入即占位零请求）。 */
export interface NotificationJobs {
  /** 列表取数（分页 + 筛选）。 */
  load?: (query: NotificationQuery) => Promise<unknown>
  /** 未读数校准（初始化 / 重连 / 聚焦）。 */
  loadUnread?: () => Promise<unknown>
  /** 详情取数（查看即已读，幂等）。 */
  detail?: (id: string) => Promise<unknown>
  /** 批量已读（返回服务端未读数校准值）。 */
  markRead?: (ids: readonly string[]) => Promise<{ unreadCount?: number } | undefined>
  /** 全部已读。 */
  markAllRead?: () => Promise<{ unreadCount?: number } | undefined>
  /** 单条删除（软删除）。 */
  remove?: (id: string) => Promise<boolean | undefined>
}

/** 实时适配器（宿主注入；未注入即轮询占位；核心不依赖 socket.io）。 */
export interface NotificationRealtimeAdapter {
  /** 建立连接。 */
  connect(): void
  /** 断开连接（幂等）。 */
  disconnect(): void
  /** 订阅连接状态。 */
  onState(handler: (state: NotificationConnectionState) => void): () => void
  /** 订阅实时消息。 */
  onMessage(handler: (payload: NotificationRealtimePayload) => void): () => void
}

/** 通知中心编排阶段。 */
export type NotificationPhase = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

/** 通知中心编排能力基类（抽象）。 */
export abstract class BaseNotificationCenter extends BaseNotice {
  /** 能力键。 */
  readonly identifier: string = 'notification-center'
  /** 依赖登记。 */
  override readonly depends: readonly string[] = ['notice']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false

  /**
   * 切换就绪态（就绪时按有无实时适配器启动连接或轮询）。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    this.ready = value
    if (!value) {
      this.stopPolling()
    } else if (this.hasRealtime) {
      this.connect()
    } else {
      this.startPolling()
    }
    this.emitUpdate()
  }
  /** 编排阶段。 */
  phase: NotificationPhase = 'idle'
  /** 错误文案。 */
  errorMessage = ''
  /** 消息清单。 */
  readonly items: NotificationMessage[] = []
  /** 总数。 */
  total = 0
  /** 页码（自 1）。 */
  page = 1
  /** 页长。 */
  pageSize: number = NOTIFICATION_PAGE_SIZE_DEFAULT
  /** 类型筛选。 */
  typeFilter: NotificationMessageType | 'all' = 'all'
  /** 已读筛选。 */
  readFilter: NotificationReadFilter = 'all'
  /** 未读数（角标口径；本地乐观 + 服务端校准）。 */
  unreadCount = 0
  /** 勾选集合（批量已读）。 */
  readonly selectedIds = new Set<string>()
  /** 实时连接状态。 */
  connectionState: NotificationConnectionState = 'idle'
  /** 取数处理函数（使用方注入）。 */
  jobs: NotificationJobs = {}
  /** 实时适配器（宿主注入；未注入即轮询占位）。 */
  realtime: NotificationRealtimeAdapter | undefined

  /** 页面是否可见（轮询门控）。 */
  private pageVisible = true
  /** 轮询定时器。 */
  private pollingTimer: ReturnType<typeof setInterval> | undefined
  /** 连接状态解绑函数。 */
  private offState: (() => void) | undefined
  /** 实时消息解绑函数。 */
  private offMessage: (() => void) | undefined
  /** 是否曾经连接成功（用于区分首次连接与断线重连补偿）。 */
  private everConnected = false


  /** 列表是否加载中（命名避让组件根 `loading` 字段）。 */
  get listLoading(): boolean {
    return this.phase === 'loading'
  }

  /** 是否空态。 */
  get empty(): boolean {
    return this.phase === 'empty'
  }

  /** 是否错误态。 */
  get error(): boolean {
    return this.phase === 'error'
  }

  /** 是否进行中。 */
  get busy(): boolean {
    return this.phase === 'loading'
  }

  /** 是否已注入实时适配器。 */
  get hasRealtime(): boolean {
    return this.realtime !== undefined
  }

  /** 角标计数（夹取到上限）。 */
  get badgeCount(): number {
    return clampBadgeCount(this.unreadCount)
  }

  /** 角标文案（`0` → 空串、超上限 → `99+`）。 */
  get badgeText(): string {
    return badgeTextOf(this.unreadCount)
  }

  /** 是否显示角标。 */
  get showBadge(): boolean {
    return shouldShowBadge(this.unreadCount)
  }


  /**
   * 注入取数处理函数集。
   *
   * @param jobs 处理函数集（整体替换）。
   */
  setJobs(jobs: NotificationJobs): void {
    this.jobs = { ...jobs }
  }

  /**
   * 注入 / 移除实时适配器（移除即回落轮询占位）。
   *
   * @param adapter 适配器；`undefined` 表示移除。
   */
  setRealtime(adapter: NotificationRealtimeAdapter | undefined): void {
    if (this.realtime !== undefined) {
      this.disconnect()
    }
    this.realtime = adapter
    if (adapter !== undefined) {
      this.stopPolling()
      if (this.ready) {
        this.connect()
      }
    } else if (this.ready) {
      this.startPolling()
    }
    this.emitUpdate()
  }

  /**
   * 设置页码（夹取 `≥ 1`）。
   *
   * @param page 页码。
   */
  setPage(page: number): void {
    this.page = Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1
    this.emitUpdate()
  }

  /**
   * 设置页长（夹取 `1 ~ NOTIFICATION_PAGE_SIZE_MAX`）。
   *
   * @param size 页长。
   */
  setPageSize(size: number): void {
    const value = Number.isFinite(size) && size >= 1 ? Math.floor(size) : NOTIFICATION_PAGE_SIZE_DEFAULT
    this.pageSize = Math.min(value, NOTIFICATION_PAGE_SIZE_MAX)
    this.emitUpdate()
  }

  /**
   * 设置类型筛选。
   *
   * @param type 类型 / `all`。
   */
  setTypeFilter(type: NotificationMessageType | 'all'): void {
    this.typeFilter = type
    this.emitUpdate()
  }

  /**
   * 设置已读筛选。
   *
   * @param read 已读档。
   */
  setReadFilter(read: NotificationReadFilter): void {
    this.readFilter = read
    this.emitUpdate()
  }

  /**
   * 设置页面可见性（恢复可见时立即校准一次未读数）。
   *
   * @param visible 是否可见。
   */
  setVisible(visible: boolean): void {
    this.pageVisible = visible
    if (visible && this.ready && !this.hasRealtime) {
      void this.syncUnread()
    }
  }

  /**
   * 直接设置未读数（本地校准 / 多标签同步用，不发请求）。
   *
   * @param value 未读数。
   */
  setUnreadCount(value: number): void {
    this.unreadCount = parseUnreadCount(value)
    this.emitUpdate()
  }

  /**
   * 覆盖消息清单（种子 / 外部驱动，不发请求）。
   *
   * @param items 消息数组。
   */
  setItems(items: readonly NotificationMessage[]): void {
    this.items.splice(0, this.items.length, ...normalizeNotificationMessages(items))
    this.emitUpdate()
  }

  /** 当前查询条件。 */
  private currentQuery(): NotificationQuery {
    return {
      type: this.typeFilter,
      read: this.readFilter,
      page: this.page,
      pageSize: this.pageSize,
    }
  }

  /** 当前查询参数（与后端契约同源）。 */
  queryParams(): Record<string, unknown> {
    return buildNotificationParams(this.currentQuery())
  }

  /** 复制当前状态快照（回滚用）。 */
  snapshot(): NotificationSnapshot {
    return restoreSnapshot({ items: this.items, unreadCount: this.unreadCount, total: this.total })
  }

  /**
   * 取最近 N 条（铃铛下拉）。
   *
   * @param limit 条数（缺省 `NOTIFICATION_RECENT_LIMIT`）。
   * @returns 最近 N 条。
   */
  recent(limit?: number): NotificationMessage[] {
    return recentMessages(this.items, limit)
  }

  /**
   * 列表取数（未就绪 / 未注入处理函数不请求）。
   *
   * @returns 归一消息数组或 `undefined`。
   */
  async load(): Promise<NotificationMessage[] | undefined> {
    if (!this.ready || this.jobs.load === undefined) {
      return undefined
    }
    this.requestCount += 1
    this.phase = 'loading'
    this.emitUpdate()
    try {
      const page = normalizeNotificationPage(await this.jobs.load(this.currentQuery()))
      this.applyPage(page)
      this.phase = this.items.length > 0 ? 'ready' : 'empty'
      this.errorMessage = ''
      this.emitUpdate()
      return this.items.map((item) => ({ ...item }))
    } catch (error) {
      this.phase = 'error'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseNotificationCenter.load' })
      this.emitUpdate()
      return undefined
    }
  }

  /**
   * 重新取数（等价 `load`）。
   *
   * @returns 归一消息数组或 `undefined`。
   */
  async refresh(): Promise<NotificationMessage[] | undefined> {
    return this.load()
  }

  /**
   * 未读数校准（初始化 / 重连 / 聚焦；未就绪 / 未注入不请求）。
   *
   * @returns 校准后的未读数或 `undefined`。
   */
  async syncUnread(): Promise<number | undefined> {
    if (!this.ready || this.jobs.loadUnread === undefined) {
      return undefined
    }
    this.requestCount += 1
    try {
      const count = parseUnreadCount(await this.jobs.loadUnread())
      this.unreadCount = count
      this.emitUpdate()
      return count
    } catch (error) {
      this.reportError(error, { scope: 'BaseNotificationCenter.syncUnread' })
      return undefined
    }
  }

  /**
   * 详情取数（查看即已读，幂等；未就绪 / 未注入不请求）。
   *
   * @param id 通知 id。
   * @returns 归一消息或 `undefined`。
   */
  async loadDetail(id: string): Promise<NotificationMessage | undefined> {
    if (!this.ready || this.jobs.detail === undefined) {
      return undefined
    }
    this.requestCount += 1
    try {
      const message = normalizeNotificationMessage(await this.jobs.detail(id))
      return message
    } catch (error) {
      this.reportError(error, { scope: 'BaseNotificationCenter.loadDetail' })
      return undefined
    }
  }

  /**
   * 单条已读（本地乐观 + 失败回滚；已读项幂等）。
   *
   * @param id 通知 id。
   * @returns 是否成功（已读 / 本地变更成功）。
   */
  async markRead(id: string): Promise<boolean> {
    return this.commitRead([id])
  }

  /**
   * 批量已读（去重 + 上限截断；本地乐观 + 失败回滚）。
   *
   * @param ids 通知 id 集合。
   * @returns 是否成功。
   */
  async readBatch(ids: readonly string[]): Promise<boolean> {
    const unique = [...new Set(ids)].slice(0, NOTIFICATION_BATCH_MAX)
    if (unique.length === 0) {
      return false
    }
    return this.commitRead(unique)
  }

  /**
   * 全部已读（本地乐观 + 失败回滚）。
   *
   * @returns 是否成功。
   */
  async markAllRead(): Promise<boolean> {
    const before = this.snapshot()
    const { snapshot: next, changed } = applyOptimisticReadAll(before)
    const apply = (): void => {
      this.items.splice(0, this.items.length, ...next.items)
      this.unreadCount = next.unreadCount
      this.emitUpdate()
    }
    apply()
    if (changed === 0 || !this.ready || this.jobs.markAllRead === undefined) {
      return true
    }
    try {
      const result = await this.jobs.markAllRead()
      if (result?.unreadCount !== undefined) {
        this.unreadCount = parseUnreadCount(result.unreadCount)
      }
      this.emitUpdate()
      return true
    } catch (error) {
      this.items.splice(0, this.items.length, ...before.items)
      this.unreadCount = before.unreadCount
      this.total = before.total
      this.reportError(error, { scope: 'BaseNotificationCenter.markAllRead' })
      this.emitUpdate()
      return false
    }
  }

  /**
   * 单条删除（本地乐观 + 失败回滚）。
   *
   * @param id 通知 id。
   * @returns 是否成功。
   */
  async remove(id: string): Promise<boolean> {
    const before = this.snapshot()
    const { snapshot: next, changed } = applyOptimisticRemove(before, id)
    if (changed === 0) {
      return false
    }
    this.items.splice(0, this.items.length, ...next.items)
    this.unreadCount = next.unreadCount
    this.total = next.total
    this.emitUpdate()
    if (!this.ready || this.jobs.remove === undefined) {
      return true
    }
    try {
      const ok = await this.jobs.remove(id)
      if (ok === false) {
        this.restore(before)
        return false
      }
      return true
    } catch (error) {
      this.restore(before)
      this.reportError(error, { scope: 'BaseNotificationCenter.remove' })
      return false
    }
  }

  /**
   * 切换勾选（批量已读）。
   *
   * @param id 通知 id。
   */
  toggleSelect(id: string): void {
    if (this.selectedIds.has(id)) {
      this.selectedIds.delete(id)
    } else {
      this.selectedIds.add(id)
    }
    this.emitUpdate()
  }

  /** 勾选当前页全部消息。 */
  selectAllCurrent(): void {
    for (const item of this.items) {
      this.selectedIds.add(item.id)
    }
    this.emitUpdate()
  }

  /** 清空勾选。 */
  clearSelection(): void {
    this.selectedIds.clear()
    this.emitUpdate()
  }

  /**
   * 接收实时增量（去重 + 角标 +1）。
   *
   * @param payload 实时载荷。
   */
  applyRealtime(payload: NotificationRealtimePayload): void {
    if (!this.ready) {
      return
    }
    const next = applyIncoming(this.snapshot(), payload)
    this.items.splice(0, this.items.length, ...next.items)
    this.unreadCount = next.unreadCount
    this.total = next.total
    this.emitUpdate()
  }

  /**
   * 断线重连补偿：拉取未读数校准。
   *
   * @returns 校准后的未读数或 `undefined`。
   */
  async compensate(): Promise<number | undefined> {
    return this.syncUnread()
  }

  /** 建立实时连接（未注入适配器不动作；重复调用幂等）。 */
  connect(): void {
    const adapter = this.realtime
    if (adapter === undefined || this.offState !== undefined) {
      return
    }
    this.connectionState = 'connecting'
    this.offState = adapter.onState((state) => this.handleState(state))
    this.offMessage = adapter.onMessage((payload) => this.applyRealtime(payload))
    adapter.connect()
    this.emitUpdate()
  }

  /** 断开实时连接并解绑（幂等）。 */
  disconnect(): void {
    this.offState?.()
    this.offMessage?.()
    this.offState = undefined
    this.offMessage = undefined
    this.realtime?.disconnect()
    this.connectionState = 'offline'
    this.emitUpdate()
  }

  /** 启动轮询占位（仅就绪且未注入实时适配器；幂等）。 */
  startPolling(): void {
    if (!isPollingNeeded(this.ready, this.hasRealtime) || this.pollingTimer !== undefined) {
      return
    }
    this.pollingTimer = setInterval(() => {
      if (this.pageVisible) {
        void this.syncUnread()
      }
    }, NOTIFICATION_POLL_INTERVAL)
  }

  /** 停止轮询占位（幂等）。 */
  stopPolling(): void {
    if (this.pollingTimer !== undefined) {
      clearInterval(this.pollingTimer)
      this.pollingTimer = undefined
    }
  }

  /** 释放：停轮询 + 断连 + 解绑订阅。 */
  protected override onDispose(): void {
    this.stopPolling()
    this.offState?.()
    this.offMessage?.()
    this.offState = undefined
    this.offMessage = undefined
    this.realtime?.disconnect()
    super.onDispose()
  }

  /**
   * 提交已读（本地乐观 + 失败回滚）。
   *
   * @param ids 去重后的目标 id。
   * @returns 是否成功。
   */
  private async commitRead(ids: readonly string[]): Promise<boolean> {
    const before = this.snapshot()
    const { snapshot: next, changed } = applyOptimisticRead(before, ids)
    if (changed === 0) {
      return true
    }
    this.items.splice(0, this.items.length, ...next.items)
    this.unreadCount = next.unreadCount
    this.emitUpdate()
    if (!this.ready || this.jobs.markRead === undefined) {
      return true
    }
    try {
      const result = await this.jobs.markRead(ids)
      if (result?.unreadCount !== undefined) {
        this.unreadCount = parseUnreadCount(result.unreadCount)
      }
      this.emitUpdate()
      return true
    } catch (error) {
      this.restore(before)
      this.reportError(error, { scope: 'BaseNotificationCenter.commitRead' })
      return false
    }
  }

  /**
   * 应用列表结果（消息 / 总数 / 未读数校准）。
   *
   * @param page 归一列表结果。
   */
  private applyPage(page: { items: NotificationMessage[]; total: number; unreadCount?: number }): void {
    this.items.splice(0, this.items.length, ...page.items)
    this.total = page.total
    if (page.unreadCount !== undefined) {
      this.unreadCount = page.unreadCount
    }
  }

  /**
   * 回滚到快照。
   *
   * @param snapshot 目标快照。
   */
  private restore(snapshot: NotificationSnapshot): void {
    this.items.splice(0, this.items.length, ...snapshot.items)
    this.unreadCount = snapshot.unreadCount
    this.total = snapshot.total
    this.emitUpdate()
  }

  /**
   * 处理连接状态迁移（`reconnecting → connected` 触发补偿）。
   *
   * @param state 连接状态。
   */
  private handleState(state: NotificationConnectionState): void {
    const previous = this.connectionState
    this.connectionState = state
    if (state === 'connected') {
      if (this.everConnected && previous !== 'connected') {
        void this.compensate()
      }
      this.everConnected = true
    }
    this.emitUpdate()
  }

  /** 广播更新（已释放则忽略）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
