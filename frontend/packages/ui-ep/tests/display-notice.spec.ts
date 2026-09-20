// kiwi_id: 959
/** 通知与消息用例（07-4）：投影薄适配 + 契约套件 + 四件真实实现 + 实时 / 轮询 / 多标签同步。 */

import type { NotificationJobs, NotificationRealtimeAdapter } from '@bms/core'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import NoticeBell from '../src/components/notice/NoticeBell.vue'
import NoticeDetail from '../src/components/notice/NoticeDetail.vue'
import NoticeList from '../src/components/notice/NoticeList.vue'
import NoticeMessageItem from '../src/components/notice/NoticeMessageItem.vue'
import { useBaseNotification } from '../src'
import { createNotificationChannel } from '../src/utils/notificationChannel'
import { startUnreadPolling } from '../src/utils/notificationRealtime'
import {
  NOTIFICATION_CONTRACT_PAGE,
  createNotificationRealtimeStub,
  describeNotificationContract,
  type NotificationContractAdapter,
  type NotificationContractTarget,
} from '@bms/core/testing'

/** 消息样例。 */
const items = [
  { id: 'n1', title: '系统维护通知', content: '系统将于今晚维护', type: 'notice' as const, read: false, createdAt: '2026-09-20T10:00:00Z' },
  { id: 'n2', title: '待审批：采购申请', type: 'todo' as const, read: true, createdAt: '2026-09-19T10:00:00Z', bizType: 'wf_task', bizId: '42' },
]

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

/** 通知契约目标工厂（适配器接 ui-ep 投影）。 */
function makeNotificationTarget(): NotificationContractTarget {
  const api = useBaseNotification()
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get requestCount() {
      return api.center.requestCount
    },
    get phase() {
      return api.phase.value
    },
    get items() {
      return api.items.value
    },
    get total() {
      return api.total.value
    },
    get page() {
      return api.page.value
    },
    get pageSize() {
      return api.pageSize.value
    },
    get unreadCount() {
      return api.unreadCount.value
    },
    get badgeText() {
      return api.badgeText.value
    },
    get showBadge() {
      return api.showBadge.value
    },
    get connectionState() {
      return api.connectionState.value
    },
    setReady: (value) => api.setReady(value),
    setJobs: (jobs) => api.setJobs(jobs as NotificationJobs),
    setRealtime: (adapter) => api.setRealtime(adapter as NotificationRealtimeAdapter | undefined),
    setPage: (page) => api.setPage(page),
    setPageSize: (size) => api.setPageSize(size),
    setTypeFilter: (type) => api.setTypeFilter(type as 'notice' | 'todo' | 'system' | 'all'),
    setReadFilter: (read) => api.setReadFilter(read as 'all' | 'unread' | 'read'),
    recent: (limit) => api.recent(limit),
    load: () => api.load(),
    syncUnread: () => api.syncUnread(),
    loadDetail: (id) => api.loadDetail(id),
    markRead: (id) => api.markRead(id),
    readBatch: (ids) => api.readBatch(ids),
    markAllRead: () => api.markAllRead(),
    remove: (id) => api.remove(id),
    applyRealtime: (payload) =>
      api.applyRealtime(payload as Parameters<typeof api.applyRealtime>[0]),
    compensate: () => api.compensate(),
    connect: () => api.connect(),
    disconnect: () => api.disconnect(),
    dispose: () => api.center.dispose(),
  }
}

describeNotificationContract('通知契约（useBaseNotification 适配）', makeNotificationTarget)

describe('useBaseNotification 投影', () => {
  it('占位态降级且零请求', async () => {
    const api = useBaseNotification()
    expect(api.ready.value).toBe(false)
    expect(api.degraded.value).toBe(true)
    await api.load()
    expect(api.center.requestCount).toBe(0)
  })

  it('就绪注入取数后装载并同步角标', async () => {
    const api = useBaseNotification({ ready: true, jobs: { load: async () => NOTIFICATION_CONTRACT_PAGE } })
    await api.load()
    expect(api.items.value).toHaveLength(2)
    expect(api.unreadCount.value).toBe(1)
    expect(api.badgeText.value).toBe('1')
    expect(api.showBadge.value).toBe(true)
  })

  it('角标 99+ 与本地乐观已读', async () => {
    const api = useBaseNotification({
      ready: true,
      items,
      unreadCount: 150,
      jobs: { markRead: async () => ({ unreadCount: 1 }) },
    })
    expect(api.badgeText.value).toBe('99+')
    await api.markRead('n1')
    expect(api.items.value.find((item) => item.id === 'n1')?.read).toBe(true)
  })

  it('提交失败回滚', async () => {
    const api = useBaseNotification({
      ready: true,
      items,
      unreadCount: 1,
      jobs: {
        markRead: async () => {
          throw new Error('失败')
        },
      },
    })
    await api.markRead('n1')
    expect(api.items.value.find((item) => item.id === 'n1')?.read).toBe(false)
    expect(api.unreadCount.value).toBe(1)
  })

  it('实时增量与断线补偿', async () => {
    const api = useBaseNotification({ ready: true, items, unreadCount: 0, jobs: { loadUnread: async () => 6 } })
    api.applyRealtime({ id: 'n3', title: '新通知', type: 'notice' })
    expect(api.unreadCount.value).toBe(1)
    const stub = createNotificationRealtimeStub()
    api.setRealtime(stub.adapter as NotificationContractAdapter as NotificationRealtimeAdapter)
    stub.emitState('connecting')
    stub.emitState('connected')
    stub.emitState('reconnecting')
    stub.emitState('connected')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(api.unreadCount.value).toBe(6)
  })
})

describe('NoticeMessageItem 消息项', () => {
  it('渲染类型 / 标题 / 时间 / 未读并上抛事件', async () => {
    const wrapper = mount(NoticeMessageItem, { props: { message: items[0]!, showRemove: true } })
    expect(wrapper.find('[data-test="notice-type"]').text()).toBe('站内信')
    expect(wrapper.find('[data-test="notice-title"]').text()).toBe('系统维护通知')
    expect(wrapper.find('[data-test="notice-unread"]').exists()).toBe(true)

    await wrapper.trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual([items[0]])
    await wrapper.find('[data-test="mark-read"]').trigger('click')
    expect(wrapper.emitted('read')?.[0]).toEqual(['n1'])
    await wrapper.find('[data-test="remove"]').trigger('click')
    expect(wrapper.emitted('remove')?.[0]).toEqual(['n1'])
  })

  it('已读项不渲染未读点；有跳转目标时标记可跳转', () => {
    const wrapper = mount(NoticeMessageItem, { props: { message: items[1]! } })
    expect(wrapper.find('[data-test="notice-unread"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="notice-jumpable"]').exists()).toBe(true)
  })
})

describe('NoticeList 通知列表', () => {
  it('占位降级与就绪渲染（冻结契约保持）', () => {
    const placeholder = mount(NoticeList, { props: {} })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('通知数据未就绪')

    const wrapper = mount(NoticeList, { props: { ready: true, items, unreadCount: 1 } })
    expect(wrapper.find('[data-test="unread-count"]').text()).toContain('1')
    expect(wrapper.find('[data-test="notice-n1"]').exists()).toBe(true)
  })

  it('筛选与批量已读上抛', async () => {
    const wrapper = mount(NoticeList, {
      props: { ready: true, items, showFilter: true, selectable: true, selectedIds: ['n1'] },
    })
    await wrapper.find('[data-test="filter-type"]').setValue('todo')
    expect(wrapper.emitted('update:typeFilter')?.[0]).toEqual(['todo'])
    await wrapper.find('[data-test="filter-read"]').setValue('unread')
    expect(wrapper.emitted('update:readFilter')?.[0]).toEqual(['unread'])
    await wrapper.find('[data-test="read-batch"]').trigger('click')
    expect(wrapper.emitted('read-batch')?.[0]).toEqual([['n1']])
    await wrapper.find('[data-test="select-all"]').trigger('change')
    expect(wrapper.emitted('update:selectedIds')?.[0]?.[0]).toEqual(['n1', 'n2'])
  })

  it('分页上抛与空 / 错误 / 骨架态', async () => {
    const wrapper = mount(NoticeList, { props: { ready: true, items, total: 60, pageSize: 20, page: 1 } })
    await wrapper.find('[data-test="pagination"] button:last-child').trigger('click')
    expect(wrapper.emitted('update:page')?.[0]).toEqual([2])

    expect(mount(NoticeList, { props: { ready: true, items: [] } }).find('[data-test="empty"]').exists()).toBe(true)
    expect(mount(NoticeList, { props: { ready: true, error: true } }).find('[data-test="error"]').exists()).toBe(true)
    expect(mount(NoticeList, { props: { ready: true, firstLoad: true } }).find('[data-test="skeleton"]').exists()).toBe(true)
  })
})

describe('NoticeBell 顶栏铃铛', () => {
  it('占位降级', () => {
    const wrapper = mount(NoticeBell, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('通知数据未就绪')
  })

  it('角标 99+ 与下拉最近 5 条', async () => {
    const many = Array.from({ length: 8 }, (_, index) => ({
      id: `n${index}`,
      title: `通知${index}`,
      read: false,
      createdAt: `2026-09-${String(20 - index).padStart(2, '0')}T10:00:00Z`,
    }))
    const wrapper = mount(NoticeBell, { props: { ready: true, unreadCount: 120, items: many, recentLimit: 5 } })
    expect(wrapper.find('[data-test="notice-badge"]').text()).toBe('99+')
    await wrapper.find('.bms-notice-bell__trigger').trigger('click')
    expect(wrapper.findAll('[data-test="notice-recent"] li')).toHaveLength(5)
  })

  it('0 不显示角标；查看全部 / 全部已读上抛', async () => {
    const wrapper = mount(NoticeBell, { props: { ready: true, unreadCount: 0, items } })
    expect(wrapper.find('[data-test="notice-badge"]').exists()).toBe(false)
    await wrapper.find('.bms-notice-bell__trigger').trigger('click')
    await wrapper.find('[data-test="view-all"]').trigger('click')
    expect(wrapper.emitted('view-all')).toHaveLength(1)
    await wrapper.find('[data-test="read-all"]').trigger('click')
    expect(wrapper.emitted('read-all')).toHaveLength(1)
  })
})

describe('NoticeDetail 通知详情', () => {
  const drawerStub = {
    ElDrawer: { props: ['title', 'modelValue'], template: '<div><slot /><slot name="footer" /></div>' },
  }

  it('占位降级', () => {
    const wrapper = mount(NoticeDetail, { props: { modelValue: true }, global: { stubs: drawerStub } })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('通知数据未就绪')
  })

  it('打开未读消息查看即已读（幂等）并可跳转', async () => {
    const wrapper = mount(NoticeDetail, { props: { modelValue: false, ready: true, message: items[0]! } })
    expect(wrapper.emitted('read')).toBeUndefined()
    await wrapper.setProps({ modelValue: true })
    expect(wrapper.emitted('read')?.[0]).toEqual(['n1'])
    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    expect(wrapper.emitted('read')).toHaveLength(1)
  })

  it('有跳转目标时渲染查看单据并上抛', async () => {
    const wrapper = mount(NoticeDetail, {
      props: { modelValue: true, ready: true, message: items[1]! },
      global: { stubs: drawerStub },
    })
    expect(wrapper.text()).toContain('待审批：采购申请')
    await wrapper.find('[data-test="notice-jump"]').trigger('click')
    expect(wrapper.emitted('jump')?.[0]).toEqual([{ bizType: 'wf_task', bizId: '42' }])
  })
})

describe('轮询占位与多标签同步工具', () => {
  it('轮询仅可见时触发，kick 立即执行', async () => {
    vi.useFakeTimers()
    let calls = 0
    let visible = true
    const handle = startUnreadPolling({
      intervalMs: 1000,
      visible: () => visible,
      loadUnread: async () => {
        calls += 1
      },
    })
    await vi.advanceTimersByTimeAsync(1000)
    expect(calls).toBe(1)
    visible = false
    await vi.advanceTimersByTimeAsync(2000)
    expect(calls).toBe(1)
    visible = true
    handle.kick()
    await Promise.resolve()
    expect(calls).toBe(2)
    handle.stop()
    await vi.advanceTimersByTimeAsync(1000)
    expect(calls).toBe(2)
  })

  it('多标签同步经 BroadcastChannel 广播；能力缺失静默降级', () => {
    const received: unknown[] = []
    class FakeChannel {
      static all: FakeChannel[] = []
      onmessage: ((event: { data: unknown }) => void) | null = null
      constructor(public name: string) {
        FakeChannel.all.push(this)
      }
      postMessage(message: unknown): void {
        for (const channel of FakeChannel.all) {
          if (channel !== this && channel.name === this.name) {
            channel.onmessage?.({ data: message })
          }
        }
      }
      close(): void {}
    }
    vi.stubGlobal('BroadcastChannel', FakeChannel)
    const receiver = createNotificationChannel('test:notification', (message) => received.push(message))
    const sender = createNotificationChannel('test:notification', () => {})
    sender.publish({ unreadCount: 3, action: 'read', ids: ['n1'] })
    expect(received[0]).toEqual({ unreadCount: 3, action: 'read', ids: ['n1'] })
    sender.close()
    receiver.close()

    vi.unstubAllGlobals()
    const fallback = createNotificationChannel('test:notification', () => {})
    expect(() => fallback.publish({ unreadCount: 1 })).not.toThrow()
  })
})
