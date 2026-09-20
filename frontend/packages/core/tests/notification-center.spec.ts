// kiwi_id: 959
/** 通知组件基类 / 通知中心编排能力基类用例（07-4）：契约套件 + 身份依赖 + 占位门控 + 实时 / 轮询 / 补偿。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  BaseNotification,
  BaseNotificationCenter,
  BaseNotice,
  NOTIFICATION_POLL_INTERVAL,
  validateCapabilityGraph,
  type NotificationJobs,
  type NotificationRealtimeAdapter,
  type NotificationRealtimePayload,
} from '../src'
import {
  NOTIFICATION_CONTRACT_PAGE,
  createNotificationRealtimeStub,
  describeNotificationContract,
  type NotificationContractAdapter,
  type NotificationContractTarget,
} from '../testing'

/** 具体通知基类（可实例化）。 */
class DemoNotification extends BaseNotification {}

/** 具体通知中心基类（可实例化，验证能力基类自身）。 */
class DemoCenter extends BaseNotificationCenter {}

/** 通知契约目标工厂（适配器接核心基类）。 */
function makeNotificationTarget(): NotificationContractTarget {
  const notification = new DemoNotification()
  return {
    get ready() {
      return notification.ready
    },
    get degraded() {
      return notification.degraded
    },
    get requestCount() {
      return notification.requestCount
    },
    get phase() {
      return notification.phase
    },
    get items() {
      return notification.items
    },
    get total() {
      return notification.total
    },
    get page() {
      return notification.page
    },
    get pageSize() {
      return notification.pageSize
    },
    get unreadCount() {
      return notification.unreadCount
    },
    get badgeText() {
      return notification.badgeText
    },
    get showBadge() {
      return notification.showBadge
    },
    get connectionState() {
      return notification.connectionState
    },
    setReady: (value) => notification.setReady(value),
    setJobs: (jobs) => notification.setJobs(jobs as NotificationJobs),
    setRealtime: (adapter) => notification.setRealtime(adapter as NotificationRealtimeAdapter | undefined),
    setPage: (page) => notification.setPage(page),
    setPageSize: (size) => notification.setPageSize(size),
    setTypeFilter: (type) => notification.setTypeFilter(type as Parameters<DemoNotification['setTypeFilter']>[0]),
    setReadFilter: (read) => notification.setReadFilter(read as Parameters<DemoNotification['setReadFilter']>[0]),
    recent: (limit) => notification.recent(limit),
    load: () => notification.load(),
    syncUnread: () => notification.syncUnread(),
    loadDetail: (id) => notification.loadDetail(id),
    markRead: (id) => notification.markRead(id),
    readBatch: (ids) => notification.readBatch(ids),
    markAllRead: () => notification.markAllRead(),
    remove: (id) => notification.remove(id),
    applyRealtime: (payload) => notification.applyRealtime(payload as NotificationRealtimePayload),
    compensate: () => notification.compensate(),
    connect: () => notification.connect(),
    disconnect: () => notification.disconnect(),
    dispose: () => notification.dispose(),
  }
}

describeNotificationContract('通知契约（BaseNotification 适配）', makeNotificationTarget)

afterEach(() => {
  vi.useRealTimers()
})

describe('能力身份与依赖', () => {
  it('组件基类键为 notification、父链经通知中心能力基类到 BaseNotice', () => {
    const notification = new DemoNotification()
    expect(notification.identifier).toBe('notification')
    expect(notification.depends).toEqual(['notification-center'])
    expect(notification).toBeInstanceOf(BaseNotificationCenter)
    expect(notification).toBeInstanceOf(BaseNotice)
  })

  it('能力基类键为 notification-center、依赖 notice', () => {
    const center = new DemoCenter()
    expect(center.identifier).toBe('notification-center')
    expect(center.depends).toEqual(['notice'])
  })

  it('能力登记无环且已登记', () => {
    const problems = validateCapabilityGraph().filter(
      (problem) => problem.key === 'notification-center' || problem.key === 'notification',
    )
    expect(problems).toEqual([])
  })
})

describe('展示语义（组件基类）', () => {
  it('类型语义色 / 文案 / 跳转', () => {
    const notification = new DemoNotification()
    expect(notification.messageSemantic('todo')).toBe('warning')
    expect(notification.messageLabel('system')).toBe('系统提示')
    expect(notification.jumpTargetOf({ id: 'n1', title: 'a', bizType: 'wf_task', bizId: '7' })).toEqual({
      bizType: 'wf_task',
      bizId: '7',
    })
    expect(notification.jumpTargetOf({ id: 'n2', title: 'b' })).toBeUndefined()
  })

  it('push 置顶并更新未读；unread 本地计数', () => {
    const notification = new DemoNotification()
    notification.push({ id: 'n1', title: 'a', read: false })
    notification.push({ id: 'n2', title: 'b', read: false })
    expect(notification.unread).toBe(2)
    expect(notification.items[0]?.id).toBe('n2')
  })
})

describe('占位与就绪门控', () => {
  it('未就绪时列表 / 未读 / 详情 / 补偿均零请求', async () => {
    const notification = new DemoNotification()
    notification.setJobs({
      load: async () => NOTIFICATION_CONTRACT_PAGE,
      loadUnread: async () => 3,
      detail: async () => NOTIFICATION_CONTRACT_PAGE.items[0],
    })
    await notification.load()
    await notification.syncUnread()
    await notification.loadDetail('n1')
    await notification.compensate()
    expect(notification.requestCount).toBe(0)
  })

  it('就绪未注入处理函数时零请求', async () => {
    const notification = new DemoNotification()
    notification.setReady(true)
    await notification.load()
    await notification.syncUnread()
    expect(notification.requestCount).toBe(0)
  })
})

describe('取数结算与错误', () => {
  it('取数成功置 ready，空结果置 empty', async () => {
    const notification = new DemoNotification()
    notification.setJobs({ load: async () => NOTIFICATION_CONTRACT_PAGE })
    notification.setReady(true)
    await notification.load()
    expect(notification.phase).toBe('ready')
    expect(notification.total).toBe(2)

    notification.setJobs({ load: async () => ({ items: [], total: 0 }) })
    await notification.load()
    expect(notification.phase).toBe('empty')
  })

  it('取数失败置 error 并保留错误文案', async () => {
    const notification = new DemoNotification()
    notification.setJobs({
      load: async () => {
        throw new Error('70001')
      },
    })
    notification.setReady(true)
    await notification.load()
    expect(notification.phase).toBe('error')
    expect(notification.errorMessage).toBe('70001')
  })

  it('查询条件与参数透出', () => {
    const notification = new DemoNotification()
    notification.setTypeFilter('todo')
    notification.setReadFilter('unread')
    notification.setPage(2)
    notification.setPageSize(50)
    expect(notification.queryParams()).toEqual({ type: 'todo', is_read: 0, page: 2, size: 50 })
  })
})

describe('实时适配器与轮询', () => {
  it('注入适配器即连接并派发状态；reconnecting → connected 触发补偿', async () => {
    const notification = new DemoNotification()
    let loads = 0
    notification.setJobs({ loadUnread: async () => { loads += 1; return 4 } })
    notification.setReady(true)
    const stub = createNotificationRealtimeStub()
    notification.setRealtime(stub.adapter as NotificationContractAdapter as NotificationRealtimeAdapter)
    expect(stub.calls).toContain('connect')

    stub.emitState('connecting')
    stub.emitState('connected')
    expect(loads).toBe(0)

    stub.emitState('reconnecting')
    stub.emitState('connected')
    await Promise.resolve()
    expect(loads).toBe(1)
    expect(notification.unreadCount).toBe(4)
  })

  it('未注入适配器时就绪启动轮询；不可见暂停、恢复即时校准', async () => {
    vi.useFakeTimers()
    const notification = new DemoNotification()
    let loads = 0
    notification.setJobs({
      loadUnread: async () => {
        loads += 1
        return 2
      },
    })
    notification.setReady(true)

    await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_INTERVAL)
    expect(loads).toBe(1)

    notification.setVisible(false)
    await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_INTERVAL * 2)
    expect(loads).toBe(1)

    notification.setVisible(true)
    await Promise.resolve()
    expect(loads).toBe(2)

    notification.dispose()
    await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_INTERVAL)
    expect(loads).toBe(2)
  })

  it('注入适配器时停止轮询', async () => {
    vi.useFakeTimers()
    const notification = new DemoNotification()
    let loads = 0
    notification.setJobs({ loadUnread: async () => { loads += 1; return 1 } })
    notification.setReady(true)
    const stub = createNotificationRealtimeStub()
    notification.setRealtime(stub.adapter as NotificationContractAdapter as NotificationRealtimeAdapter)
    await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_INTERVAL * 2)
    expect(loads).toBe(0)
  })
})

describe('勾选与最近', () => {
  it('勾选 / 全选当前页 / 清空', async () => {
    const notification = new DemoNotification()
    notification.setJobs({ load: async () => NOTIFICATION_CONTRACT_PAGE })
    notification.setReady(true)
    await notification.load()
    notification.toggleSelect('n1')
    expect([...notification.selectedIds]).toEqual(['n1'])
    notification.toggleSelect('n1')
    expect(notification.selectedIds.size).toBe(0)
    notification.selectAllCurrent()
    expect(notification.selectedIds.size).toBe(2)
    notification.clearSelection()
    expect(notification.selectedIds.size).toBe(0)
  })

  it('recent 返回最近 N 条', async () => {
    const notification = new DemoNotification()
    notification.setJobs({ load: async () => NOTIFICATION_CONTRACT_PAGE })
    notification.setReady(true)
    await notification.load()
    expect(notification.recent(1)).toHaveLength(1)
  })
})
