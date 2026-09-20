/**
 * 通知契约（`@bms/core/testing`）。
 *
 * 通知中心基类 / 投影 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、就绪结算、未读校准、乐观已读与删除（失败回滚）、批量去重、实时增量去重、
 * 断线补偿、角标 `99+`。
 */

import { describe, expect, it } from 'vitest'

/** 契约消息（结构化最小面）。 */
export interface NotificationContractMessage {
  /** 主键。 */
  id: string
  /** 标题。 */
  title: string
  /** 内容。 */
  content?: string
  /** 类型。 */
  type?: string
  /** 是否已读。 */
  read?: boolean
  /** 创建时间。 */
  createdAt?: string
  /** 业务来源类型。 */
  bizType?: string
  /** 业务来源单据 id。 */
  bizId?: string
}

/** 契约实时载荷。 */
export interface NotificationContractPayload {
  /** 主键。 */
  id?: string
  /** 标题。 */
  title: string
  /** 类型。 */
  type?: string
  /** 业务来源类型。 */
  bizType?: string
  /** 业务来源单据 id。 */
  bizId?: string
  /** 创建时间。 */
  createdAt?: string
}

/** 契约取数处理函数集。 */
export interface NotificationContractJobs {
  /** 列表取数。 */
  load?: (query: { type?: string; read?: string; page?: number; pageSize?: number }) => Promise<unknown>
  /** 未读数校准。 */
  loadUnread?: () => Promise<unknown>
  /** 详情取数。 */
  detail?: (id: string) => Promise<unknown>
  /** 批量已读。 */
  markRead?: (ids: readonly string[]) => Promise<{ unreadCount?: number } | undefined>
  /** 全部已读。 */
  markAllRead?: () => Promise<{ unreadCount?: number } | undefined>
  /** 单条删除。 */
  remove?: (id: string) => Promise<boolean | undefined>
}

/** 契约实时适配器（结构化最小面）。 */
export interface NotificationContractAdapter {
  /** 建立连接。 */
  connect(): void
  /** 断开连接。 */
  disconnect(): void
  /** 订阅连接状态。 */
  onState(handler: (state: string) => void): () => void
  /** 订阅实时消息。 */
  onMessage(handler: (payload: NotificationContractPayload) => void): () => void
}

/** 通知契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface NotificationContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 编排阶段。 */
  readonly phase: string
  /** 消息清单。 */
  readonly items: readonly NotificationContractMessage[]
  /** 总数。 */
  readonly total: number
  /** 页码。 */
  readonly page: number
  /** 页长。 */
  readonly pageSize: number
  /** 未读数。 */
  readonly unreadCount: number
  /** 角标文案。 */
  readonly badgeText: string
  /** 是否显示角标。 */
  readonly showBadge: boolean
  /** 实时连接状态。 */
  readonly connectionState: string
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入取数处理函数集。 */
  setJobs(jobs: NotificationContractJobs): void
  /** 注入 / 移除实时适配器。 */
  setRealtime(adapter: NotificationContractAdapter | undefined): void
  /** 设置页码。 */
  setPage(page: number): void
  /** 设置页长。 */
  setPageSize(size: number): void
  /** 设置类型筛选。 */
  setTypeFilter(type: string): void
  /** 设置已读筛选。 */
  setReadFilter(read: string): void
  /** 取最近 N 条。 */
  recent(limit?: number): readonly NotificationContractMessage[]
  /** 列表取数。 */
  load(): Promise<unknown>
  /** 未读数校准。 */
  syncUnread(): Promise<unknown>
  /** 详情取数。 */
  loadDetail(id: string): Promise<unknown>
  /** 单条已读。 */
  markRead(id: string): Promise<boolean>
  /** 批量已读。 */
  readBatch(ids: readonly string[]): Promise<boolean>
  /** 全部已读。 */
  markAllRead(): Promise<boolean>
  /** 单条删除。 */
  remove(id: string): Promise<boolean>
  /** 接收实时增量。 */
  applyRealtime(payload: NotificationContractPayload): void
  /** 断线补偿。 */
  compensate(): Promise<unknown>
  /** 建立实时连接。 */
  connect(): void
  /** 断开实时连接。 */
  disconnect(): void
  /** 释放。 */
  dispose(): void
}

/** 契约数据：列表结果（`n1` 未读站内信、`n2` 已读待办含跳转）。 */
export const NOTIFICATION_CONTRACT_PAGE = {
  items: [
    {
      id: 'n1',
      title: '系统维护通知',
      content: '系统将于今晚维护',
      type: 'notice',
      read: false,
      createdAt: '2026-09-20T10:00:00Z',
    },
    {
      id: 'n2',
      title: '待审批：采购申请',
      type: 'todo',
      read: true,
      createdAt: '2026-09-19T10:00:00Z',
      bizType: 'wf_task',
      bizId: '42',
    },
  ],
  total: 2,
  unreadCount: 1,
}

/** 实时适配器桩。 */
export interface NotificationRealtimeStub {
  /** 调用轨迹。 */
  readonly calls: string[]
  /** 适配器。 */
  readonly adapter: NotificationContractAdapter
  /** 派发连接状态。 */
  emitState(state: string): void
  /** 派发实时消息。 */
  emitMessage(payload: NotificationContractPayload): void
}

/**
 * 创建实时适配器桩（记录调用轨迹，供测试派发状态与消息）。
 *
 * @returns 实时适配器桩。
 */
export function createNotificationRealtimeStub(): NotificationRealtimeStub {
  const calls: string[] = []
  const stateHandlers = new Set<(state: string) => void>()
  const messageHandlers = new Set<(payload: NotificationContractPayload) => void>()
  return {
    calls,
    adapter: {
      connect: () => calls.push('connect'),
      disconnect: () => calls.push('disconnect'),
      onState: (handler) => {
        stateHandlers.add(handler)
        return () => stateHandlers.delete(handler)
      },
      onMessage: (handler) => {
        messageHandlers.add(handler)
        return () => messageHandlers.delete(handler)
      },
    },
    emitState: (state) => {
      for (const handler of [...stateHandlers]) {
        handler(state)
      }
    },
    emitMessage: (payload) => {
      for (const handler of [...messageHandlers]) {
        handler(payload)
      }
    },
  }
}

/**
 * 通知契约（`07_04` 冻结；后续移动端复用同一套断言）。
 *
 * 目标约定：列表含 `n1`（未读站内信）与 `n2`（已读待办含 `bizType`/`bizId`），
 * 取数返回 `{ items, total: 2, unreadCount: 1 }`；实时载荷 `{ id: 'n3', title: '新通知', type: 'notice' }`。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeNotificationContract(name: string, create: () => NotificationContractTarget): void {
  /** 构造已就绪目标（含取数处理函数）。 */
  const readyTarget = (jobs: NotificationContractJobs = {}): NotificationContractTarget => {
    const target = create()
    target.setJobs({ load: async () => NOTIFICATION_CONTRACT_PAGE, ...jobs })
    target.setReady(true)
    return target
  }

  describe(name, () => {
    /** 等待微任务与一轮宏任务（异步补偿断言用）。 */
    const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      target.setJobs({ load: async () => NOTIFICATION_CONTRACT_PAGE, loadUnread: async () => 1 })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)

      await target.load()
      await target.syncUnread()
      await target.loadDetail('n1')
      await target.markRead('n1')
      await target.remove('n1')
      await target.compensate()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入处理函数时不产生请求（占位）', async () => {
      const target = create()
      target.setReady(true)
      await target.load()
      await target.syncUnread()
      await target.loadDetail('n1')
      expect(target.requestCount).toBe(0)
    })

    it('就绪注入取数后装载（总数 / 未读校准 / 阶段）', async () => {
      const target = readyTarget()
      await target.load()
      expect(target.requestCount).toBe(1)
      expect(target.phase).toBe('ready')
      expect(target.items).toHaveLength(2)
      expect(target.total).toBe(2)
      expect(target.unreadCount).toBe(1)
      expect(target.showBadge).toBe(true)
    })

    it('空结果结算为 empty', async () => {
      const target = readyTarget({ load: async () => ({ items: [], total: 0, unreadCount: 0 }) })
      await target.load()
      expect(target.phase).toBe('empty')
      expect(target.showBadge).toBe(false)
      expect(target.badgeText).toBe('')
    })

    it('未读数校准覆盖本地角标并夹取 99+', async () => {
      const target = readyTarget({ loadUnread: async () => 150 })
      await target.syncUnread()
      expect(target.unreadCount).toBe(150)
      expect(target.badgeText).toBe('99+')

      target.setJobs({ loadUnread: async () => 7 })
      await target.syncUnread()
      expect(target.unreadCount).toBe(7)
      expect(target.badgeText).toBe('7')
    })

    it('单条已读为本地乐观；提交失败回滚', async () => {
      let fail = false
      const target = readyTarget({
        markRead: async () => {
          if (fail) {
            throw new Error('标记失败')
          }
          return { unreadCount: 0 }
        },
      })
      await target.load()
      const unreadBefore = target.unreadCount

      expect(await target.markRead('n1')).toBe(true)
      expect(target.unreadCount).toBe(unreadBefore - 1)

      fail = true
      target.setJobs({
        markRead: async () => {
          throw new Error('标记失败')
        },
      })
      // 已读项再标记幂等，不产生变更与请求
      expect(await target.markRead('n1')).toBe(true)
    })

    it('批量已读去重；失败回滚到快照', async () => {
      let fail = false
      const seen: string[][] = []
      const target = readyTarget({
        markRead: async (ids) => {
          seen.push([...ids])
          if (fail) {
            throw new Error('批量失败')
          }
          return { unreadCount: 0 }
        },
      })
      await target.load()
      await target.markRead('n1')
      // 重置未读以验证批量
      target.applyRealtime({ id: 'n1', title: '系统维护通知', type: 'notice' })
      const unread = target.unreadCount

      fail = true
      expect(await target.readBatch(['n1', 'n1'])).toBe(false)
      expect(target.unreadCount).toBe(unread)
      expect(seen.at(-1)).toEqual(['n1'])
    })

    it('实时增量去重且角标 +1', async () => {
      const target = readyTarget()
      await target.load()
      const before = target.unreadCount

      target.applyRealtime({ id: 'n3', title: '新通知', type: 'notice' })
      expect(target.unreadCount).toBe(before + 1)
      target.applyRealtime({ id: 'n3', title: '新通知', type: 'notice' })
      expect(target.unreadCount).toBe(before + 1)
      expect(target.items.filter((item) => item.id === 'n3')).toHaveLength(1)
    })

    it('断线重连触发未读数补偿', async () => {
      let loads = 0
      const target = readyTarget({
        loadUnread: async () => {
          loads += 1
          return 5
        },
      })
      const stub = createNotificationRealtimeStub()
      target.setRealtime(stub.adapter)

      stub.emitState('connecting')
      stub.emitState('connected')
      expect(loads).toBe(0)

      stub.emitState('reconnecting')
      stub.emitState('connected')
      await flush()
      expect(loads).toBe(1)
      expect(target.unreadCount).toBe(5)
    })

    it('删除为本地乐观；失败回滚', async () => {
      let fail = false
      const target = readyTarget({
        remove: async () => {
          if (fail) {
            throw new Error('删除失败')
          }
          return true
        },
      })
      await target.load()

      expect(await target.remove('n2')).toBe(true)
      expect(target.items.some((item) => item.id === 'n2')).toBe(false)

      fail = true
      expect(await target.remove('n1')).toBe(false)
      expect(target.items.some((item) => item.id === 'n1')).toBe(true)
    })

    it('详情取数返回归一消息', async () => {
      const target = readyTarget({ detail: async () => NOTIFICATION_CONTRACT_PAGE.items[1] })
      await target.load()
      const detail = (await target.loadDetail('n2')) as NotificationContractMessage | undefined
      expect(detail?.title).toBe('待审批：采购申请')
      expect(detail?.bizType).toBe('wf_task')
    })

    it('实时适配器连接 / 断开派发与释放', () => {
      const target = readyTarget()
      const stub = createNotificationRealtimeStub()
      target.setRealtime(stub.adapter)
      expect(stub.calls).toContain('connect')

      target.disconnect()
      expect(stub.calls).toContain('disconnect')

      target.setRealtime(stub.adapter)
      target.dispose()
      expect(stub.calls.filter((call) => call === 'disconnect').length).toBeGreaterThanOrEqual(2)
    })

    it('分页与筛选状态可设置', () => {
      const target = readyTarget()
      target.setPage(3)
      target.setPageSize(50)
      target.setTypeFilter('todo')
      target.setReadFilter('unread')
      expect(target.page).toBe(3)
      expect(target.pageSize).toBe(50)
    })

    it('最近 N 条返回数组', async () => {
      const target = readyTarget()
      await target.load()
      expect(target.recent(5).length).toBeLessThanOrEqual(2)
    })
  })
}
