// kiwi_id: 959
/** 通知领域纯函数用例（07-4）：归一 / 角标 / 最近 N / 筛选 / 去重合并 / 乐观与回滚 / 轮询判定。 */

import { describe, expect, it } from 'vitest'

import {
  NOTIFICATION_BADGE_MAX,
  NOTIFICATION_BATCH_MAX,
  NOTIFICATION_POLL_INTERVAL,
  applyIncoming,
  applyOptimisticRead,
  applyOptimisticReadAll,
  applyOptimisticRemove,
  badgeTextOf,
  buildNotificationParams,
  clampBadgeCount,
  connectionLabel,
  countUnread,
  filterNotificationMessages,
  hasJumpTarget,
  isPollingNeeded,
  isUnread,
  jumpTargetOf,
  mergeMessages,
  messageTypeLabel,
  normalizeNotificationMessage,
  normalizeNotificationMessages,
  normalizeNotificationPage,
  parseUnreadCount,
  recentMessages,
  resolveMessageSemantic,
  restoreSnapshot,
  shouldPoll,
  shouldShowBadge,
  type NotificationMessage,
  type NotificationSnapshot,
} from '../src'

/** 构造测试消息。 */
function message(overrides: Partial<NotificationMessage> & { id: string }): NotificationMessage {
  return { title: `标题-${overrides.id}`, ...overrides }
}

describe('消息归一', () => {
  it('缺 id / title 为脏项', () => {
    expect(normalizeNotificationMessage(null)).toBeUndefined()
    expect(normalizeNotificationMessage({ title: 'a' })).toBeUndefined()
    expect(normalizeNotificationMessage({ id: 'n1' })).toBeUndefined()
    expect(normalizeNotificationMessage({ id: 'n1', title: 'a' })?.title).toBe('a')
  })

  it('read 兼容 is_read（0 / 1 / 布尔）且缺省 false', () => {
    expect(normalizeNotificationMessage({ id: 'n1', title: 'a' })?.read).toBe(false)
    expect(normalizeNotificationMessage({ id: 'n1', title: 'a', is_read: 1 })?.read).toBe(true)
    expect(normalizeNotificationMessage({ id: 'n1', title: 'a', is_read: '0' })?.read).toBe(false)
    expect(normalizeNotificationMessage({ id: 'n1', title: 'a', read: true })?.read).toBe(true)
  })

  it('type 非白名单回落 notice；biz 字段兼容下划线', () => {
    expect(normalizeNotificationMessage({ id: 'n1', title: 'a', type: 'x' })?.type).toBe('notice')
    expect(normalizeNotificationMessage({ id: 'n1', title: 'a', type: 'todo' })?.type).toBe('todo')
    const parsed = normalizeNotificationMessage({ id: 'n1', title: 'a', biz_type: 'wf_task', biz_id: 42 })
    expect(parsed?.bizType).toBe('wf_task')
    expect(parsed?.bizId).toBe('42')
  })

  it('数组归一剔除脏项', () => {
    const list = normalizeNotificationMessages([
      { id: 'n1', title: 'a' },
      { title: 'no-id' },
      { id: 'n2', title: 'b', read: true },
    ])
    expect(list.map((item) => item.id)).toEqual(['n1', 'n2'])
  })

  it('列表结果归一（数组 / 对象 / 未读校准）', () => {
    expect(normalizeNotificationPage([{ id: 'n1', title: 'a' }]).total).toBe(1)
    const page = normalizeNotificationPage({ items: [{ id: 'n1', title: 'a' }], total: 9, unread_count: 3 })
    expect(page.total).toBe(9)
    expect(page.unreadCount).toBe(3)
    expect(normalizeNotificationPage({ items: [{ id: 'n1', title: 'a' }] }).unreadCount).toBeUndefined()
    expect(normalizeNotificationPage('x')).toEqual({ items: [], total: 0 })
  })
})

describe('角标与未读', () => {
  it('未读判定与计数', () => {
    const items = [message({ id: 'a' }), message({ id: 'b', read: true })]
    expect(isUnread(items[0] as NotificationMessage)).toBe(true)
    expect(countUnread(items)).toBe(1)
  })

  it('角标夹取与文案（0 不显示、> 上限 99+）', () => {
    expect(clampBadgeCount(-3)).toBe(0)
    expect(clampBadgeCount(NOTIFICATION_BADGE_MAX + 20)).toBe(NOTIFICATION_BADGE_MAX)
    expect(badgeTextOf(0)).toBe('')
    expect(badgeTextOf(5)).toBe('5')
    expect(badgeTextOf(99)).toBe('99')
    expect(badgeTextOf(100)).toBe('99+')
    expect(badgeTextOf(100, 9)).toBe('9+')
    expect(shouldShowBadge(0)).toBe(false)
    expect(shouldShowBadge(1)).toBe(true)
    expect(parseUnreadCount('7')).toBe(7)
    expect(parseUnreadCount(undefined)).toBe(0)
  })
})

describe('最近 N 与筛选', () => {
  const items = [
    message({ id: 'a', createdAt: '2026-09-18T10:00:00Z', type: 'notice' }),
    message({ id: 'b', createdAt: '2026-09-20T10:00:00Z', type: 'todo', read: true }),
    message({ id: 'c', createdAt: '2026-09-19T10:00:00Z', type: 'system' }),
    message({ id: 'd' }),
  ]

  it('按创建时间降序取最近 N（时间缺失最旧）', () => {
    expect(recentMessages(items).map((item) => item.id)).toEqual(['b', 'c', 'a', 'd'])
    expect(recentMessages(items, 2).map((item) => item.id)).toEqual(['b', 'c'])
  })

  it('类型 / 已读筛选', () => {
    expect(filterNotificationMessages(items, { type: 'todo' }).map((item) => item.id)).toEqual(['b'])
    expect(filterNotificationMessages(items, { read: 'unread' }).map((item) => item.id)).toEqual(['a', 'c', 'd'])
    expect(filterNotificationMessages(items, { read: 'read' }).map((item) => item.id)).toEqual(['b'])
    expect(filterNotificationMessages(items, {})).toHaveLength(4)
  })
})

describe('去重合并与实时增量', () => {
  it('按 id 更新并保原序，新项置前', () => {
    const existing = [message({ id: 'a', title: '旧' }), message({ id: 'b' })]
    const merged = mergeMessages(existing, [message({ id: 'a', title: '新' }), message({ id: 'c' })])
    expect(merged.map((item) => item.id)).toEqual(['c', 'a', 'b'])
    expect(merged.find((item) => item.id === 'a')?.title).toBe('新')
  })

  it('实时增量去重且未读 / 总数只加一次', () => {
    const snapshot: NotificationSnapshot = { items: [message({ id: 'a' })], unreadCount: 1, total: 1 }
    const once = applyIncoming(snapshot, { id: 'n3', title: '新通知', type: 'notice' })
    expect(once.items[0]?.id).toBe('n3')
    expect(once.unreadCount).toBe(2)
    expect(once.total).toBe(2)

    const twice = applyIncoming(once, { id: 'n3', title: '新通知', type: 'notice' })
    expect(twice.unreadCount).toBe(2)
    expect(twice.total).toBe(2)
    expect(twice.items.filter((item) => item.id === 'n3')).toHaveLength(1)
  })

  it('实时载荷缺 id 时按标题 / 时间派生稳定键', () => {
    const snapshot: NotificationSnapshot = { items: [], unreadCount: 0, total: 0 }
    const first = applyIncoming(snapshot, { title: '待办', createdAt: '2026-09-20T10:00:00Z' })
    const second = applyIncoming(first, { title: '待办', createdAt: '2026-09-20T10:00:00Z' })
    expect(second.items).toHaveLength(1)
    expect(second.unreadCount).toBe(1)
  })
})

describe('乐观更新与回滚', () => {
  const snapshot: NotificationSnapshot = {
    items: [message({ id: 'a' }), message({ id: 'b', read: true }), message({ id: 'c' })],
    unreadCount: 2,
    total: 3,
  }

  it('乐观已读只递减未读项', () => {
    const { snapshot: next, changed } = applyOptimisticRead(snapshot, ['a', 'b', 'absent'])
    expect(changed).toBe(1)
    expect(next.unreadCount).toBe(1)
    expect(isUnread(next.items.find((item) => item.id === 'a') as NotificationMessage)).toBe(false)

    const { changed: again } = applyOptimisticRead(next, ['a'])
    expect(again).toBe(0)
  })

  it('全部已读归零', () => {
    const { snapshot: next, changed } = applyOptimisticReadAll(snapshot)
    expect(changed).toBe(2)
    expect(next.unreadCount).toBe(0)
  })

  it('乐观删除递减未读与总数', () => {
    const { snapshot: next, changed } = applyOptimisticRemove(snapshot, 'a')
    expect(changed).toBe(1)
    expect(next.unreadCount).toBe(1)
    expect(next.total).toBe(2)

    const { changed: miss } = applyOptimisticRemove(snapshot, 'absent')
    expect(miss).toBe(0)
  })

  it('快照复制为独立引用（回滚不污染）', () => {
    const copy = restoreSnapshot(snapshot)
    copy.items[0]!.title = '改动'
    copy.items.push(message({ id: 'z' }))
    expect(snapshot.items).toHaveLength(3)
    expect(snapshot.items[0]?.title).toBe('标题-a')
  })
})

describe('展示语义与跳转', () => {
  it('类型语义色与文案', () => {
    expect(resolveMessageSemantic('notice')).toBe('info')
    expect(resolveMessageSemantic('todo')).toBe('warning')
    expect(resolveMessageSemantic('system')).toBe('primary')
    expect(resolveMessageSemantic('unknown')).toBe('info')
    expect(messageTypeLabel('notice')).toBe('站内信')
    expect(messageTypeLabel('todo')).toBe('待办提醒')
    expect(messageTypeLabel('system')).toBe('系统提示')
    expect(messageTypeLabel('unknown')).toBe('')
  })

  it('跳转目标需 bizType 与 bizId 同时存在', () => {
    const withBiz = message({ id: 'a', bizType: 'wf_task', bizId: '42' })
    expect(hasJumpTarget(withBiz)).toBe(true)
    expect(jumpTargetOf(withBiz)).toEqual({ bizType: 'wf_task', bizId: '42' })
    expect(hasJumpTarget(message({ id: 'b', bizType: 'wf_task' }))).toBe(false)
    expect(jumpTargetOf(message({ id: 'c', bizId: '1' }))).toBeUndefined()
  })
})

describe('查询参数与轮询', () => {
  it('查询参数按契约映射 is_read / size', () => {
    expect(buildNotificationParams({ type: 'all', read: 'all' })).toEqual({})
    expect(buildNotificationParams({ type: 'todo', read: 'unread', page: 2, pageSize: 20 })).toEqual({
      type: 'todo',
      is_read: 0,
      page: 2,
      size: 20,
    })
    expect(buildNotificationParams({ read: 'read' })).toEqual({ is_read: 1 })
  })

  it('批量上限常量与轮询判定', () => {
    expect(NOTIFICATION_BATCH_MAX).toBe(500)
    expect(NOTIFICATION_POLL_INTERVAL).toBe(30_000)
    expect(isPollingNeeded(true, false)).toBe(true)
    expect(isPollingNeeded(true, true)).toBe(false)
    expect(isPollingNeeded(false, false)).toBe(false)
    expect(shouldPoll(true, 0, NOTIFICATION_POLL_INTERVAL)).toBe(true)
    expect(shouldPoll(true, 0, 1000)).toBe(false)
    expect(shouldPoll(false, 0, NOTIFICATION_POLL_INTERVAL)).toBe(false)
  })

  it('连接状态文案', () => {
    expect(connectionLabel('connected')).toBe('实时已连接')
    expect(connectionLabel('reconnecting')).toBe('实时重连中')
    expect(connectionLabel('offline')).toBe('实时已断开')
    expect(connectionLabel('idle')).toBe('实时未连接')
  })
})
