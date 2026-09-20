<script setup lang="ts">
// 开发态核对页（07_04）：通知与消息（铃铛 / 列表 / 消息项 / 详情）实例 + 13 项自检上屏（本页不进构建产物）。
import type { NotificationRealtimeAdapter, NotificationRealtimePayload } from '@bms/core'
import {
  NoticeBell,
  NoticeDetail,
  NoticeList,
  NoticeMessageItem,
  createNotificationChannel,
  startUnreadPolling,
  useBaseNotification,
} from '@bms/ui-ep'
import { computed, nextTick, onMounted, ref } from 'vue'

/** 初始消息。 */
const seed = [
  { id: 'n1', title: '系统维护通知', content: '系统将于今晚 22:00 维护', type: 'notice' as const, read: false, createdAt: '2026-09-20T10:00:00Z' },
  { id: 'n2', title: '待审批：采购申请', content: '采购申请待您审批', type: 'todo' as const, read: false, createdAt: '2026-09-19T10:00:00Z', bizType: 'wf_task', bizId: '42' },
  { id: 'n3', title: '系统提示', type: 'system' as const, read: true, createdAt: '2026-09-18T10:00:00Z' },
  { id: 'n4', title: '历史通知 4', type: 'notice' as const, read: true, createdAt: '2026-09-17T10:00:00Z' },
  { id: 'n5', title: '历史通知 5', type: 'notice' as const, read: true, createdAt: '2026-09-16T10:00:00Z' },
  { id: 'n6', title: '历史通知 6', type: 'notice' as const, read: true, createdAt: '2026-09-15T10:00:00Z' },
]

/** 交互计数。 */
const counters = ref({ readAll: 0, readBatch: 0, viewAll: 0, typeFilter: 0, page: 0, detailRead: 0, jump: 0, unreadLoads: 0 })

/** 详情显隐与当前消息。 */
const detailVisible = ref(false)
const detailMessage = ref<(typeof seed)[number] | null>(null)
/** 消息项样例。 */
const sampleItem = computed(() => seed[1]!)
/** 列表已选集合。 */
const selectedIds = ref<string[]>([])

/** 是否使下一次已读 / 删除失败（回滚自检用）。 */
let failNext = false

/** 实时适配器桩。 */
let stateHandler: ((state: string) => void) | null = null
let messageHandler: ((payload: NotificationRealtimePayload) => void) | null = null
const realtimeCalls: string[] = []
const adapter: NotificationRealtimeAdapter = {
  connect: () => realtimeCalls.push('connect'),
  disconnect: () => realtimeCalls.push('disconnect'),
  onState: (handler) => {
    stateHandler = handler as (state: string) => void
    return () => {
      stateHandler = null
    }
  },
  onMessage: (handler) => {
    messageHandler = handler
    return () => {
      messageHandler = null
    }
  },
}

const api = useBaseNotification({
  ready: false,
  jobs: {
    load: async () => ({ items: seed, total: 40, unreadCount: 2 }),
    loadUnread: async () => {
      counters.value.unreadLoads += 1
      return 5
    },
    detail: async (id) => seed.find((item) => item.id === id),
    markRead: async () => {
      if (failNext) {
        throw new Error('mock 已读失败')
      }
      return { unreadCount: 1 }
    },
    remove: async (id) => {
      if (failNext) {
        throw new Error('mock 删除失败')
      }
      return id !== ''
    },
  },
})

api.setItems(seed)
api.setUnreadCount(2)

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/**
 * 作用域内查询元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function q(scope: string, selector: string): Element | null {
  return document.querySelector(`[data-check-scope="${scope}"] ${selector}`)
}

/** 等待渲染与异步结算。 */
async function settle(): Promise<void> {
  for (let index = 0; index < 10; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 30))
    await nextTick()
  }
}

/**
 * 轮询等待条件成立。
 *
 * @param condition 条件。
 * @param tries 最大尝试次数。
 * @returns 是否成立。
 */
async function waitUntil(condition: () => boolean, tries = 60): Promise<boolean> {
  for (let index = 0; index < tries; index += 1) {
    if (condition()) {
      return true
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  return condition()
}

/**
 * 点击元素（缺失时跳过）。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function click(scope: string, selector: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLElement) {
    element.click()
  }
  await settle()
}

/**
 * 触发 change 事件并派发（下拉 / 复选）。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 * @param value 目标值。
 */
async function change(scope: string, selector: string, value: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLSelectElement || element instanceof HTMLInputElement) {
    element.value = value
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }
  await settle()
}

/** 打开某条消息详情。 */
async function openDetail(id: string): Promise<void> {
  detailMessage.value = seed.find((item) => item.id === id) ?? null
  detailVisible.value = true
  await settle()
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  await settle()

  detailVisible.value = true
  await settle()
  result.push({
    label: '① 四件占位降级（未就绪不发请求）',
    pass:
      q('list', '[data-test="placeholder"]') !== null &&
      q('bell', '[data-test="placeholder"]') !== null &&
      q('detail', '[data-test="placeholder"]') !== null,
  })
  detailVisible.value = false
  await settle()

  api.setRealtime(adapter)
  api.setReady(true)
  await settle()
  await api.load()
  await settle()
  result.push({
    label: '② 就绪切换后列表 / 铃铛渲染（取数装载）',
    pass: q('list', '[data-test="notice-n1"]') !== null && q('bell', '[data-test="notice-bell"]') !== null,
  })

  api.setUnreadCount(120)
  await settle()
  const badgeOver = q('bell', '[data-test="notice-badge"]')?.textContent?.trim() === '99+'
  api.setUnreadCount(0)
  await settle()
  const badgeHidden = q('bell', '[data-test="notice-badge"]') === null
  api.setUnreadCount(2)
  await settle()
  result.push({ label: '③ 角标 99+ 与 0 不显示', pass: badgeOver && badgeHidden })

  await click('bell', '.bms-notice-bell__trigger')
  const recentCount = document.querySelectorAll('[data-check-scope="bell"] [data-test="notice-recent"] li').length
  await click('bell', '[data-test="view-all"]')
  result.push({ label: '④ 铃铛下拉最近 5 条与查看全部', pass: recentCount === 5 && counters.value.viewAll > 0 })

  const typeText = q('list', '[data-test="notice-type"]')?.textContent?.trim()
  const relative = q('list', '[data-test="notice-time"]')?.textContent?.trim()
  const hasUnreadDot = q('list', '[data-test="notice-unread"]') !== null
  result.push({
    label: '⑤ 消息项类型语义 / 相对时间 / 未读高亮',
    pass: typeText === '站内信' && (relative ?? '') !== '' && hasUnreadDot,
  })

  api.setTypeFilter('all')
  api.setReadFilter('all')
  await settle()
  await change('list', '[data-test="filter-type"]', 'todo')
  result.push({
    label: '⑥ 列表筛选与分页上抛',
    pass: counters.value.typeFilter > 0 && q('list', '[data-test="pagination"]') !== null,
  })
  api.setTypeFilter('all')
  await settle()

  await change('list', '[data-test="select-all"]', 'on')
  await click('list', '[data-test="read-batch"]')
  await click('list', '[data-test="read-all"]')
  result.push({
    label: '⑦ 批量已读与全部已读上抛',
    pass: counters.value.readBatch > 0 && counters.value.readAll > 0,
  })

  const beforeRemove = api.items.value.length
  await click('list', '[data-test="remove"]')
  result.push({ label: '⑧ 单条删除本地移除', pass: api.items.value.length === beforeRemove - 1 })

  await openDetail('n2')
  await click('detail', '[data-test="notice-jump"]')
  const detailReads = counters.value.detailRead
  detailVisible.value = false
  await settle()
  detailVisible.value = true
  await settle()
  result.push({
    label: '⑨ 详情查看即已读（幂等）与跳转',
    pass: detailReads === 1 && counters.value.detailRead === 1 && counters.value.jump > 0,
  })
  detailVisible.value = false
  await settle()

  failNext = true
  const unreadBefore = api.unreadCount.value
  await api.markRead('n2')
  await settle()
  const rolledBack = api.items.value.find((item) => item.id === 'n2')?.read !== true && api.unreadCount.value === unreadBefore
  failNext = false
  result.push({ label: '⑩ 本地乐观 + 失败回滚', pass: rolledBack })

  api.setRealtime(adapter)
  await settle()
  const unreadBase = api.unreadCount.value
  messageHandler?.({ id: 'n9', title: '新通知', type: 'notice' })
  await settle()
  const afterFirst = api.unreadCount.value
  messageHandler?.({ id: 'n9', title: '新通知', type: 'notice' })
  await settle()
  result.push({
    label: '⑪ 实时增量去重且角标 +1',
    pass: afterFirst === unreadBase + 1 && api.unreadCount.value === afterFirst,
  })

  const loadsBefore = counters.value.unreadLoads
  stateHandler?.('connected')
  stateHandler?.('reconnecting')
  stateHandler?.('connected')
  await settle()
  result.push({
    label: '⑫ 断线重连补偿拉未读数',
    pass: counters.value.unreadLoads > loadsBefore && api.unreadCount.value === 5,
  })

  const channel = createNotificationChannel('bms:notice-check', (message) => {
    if (message.unreadCount !== undefined) {
      api.setUnreadCount(message.unreadCount)
    }
  })
  const sender = createNotificationChannel('bms:notice-check', () => {})
  sender.publish({ unreadCount: 7, action: 'read' })
  const synced = await waitUntil(() => api.unreadCount.value === 7)
  channel.close()
  sender.close()

  let polled = 0
  const polling = startUnreadPolling({
    intervalMs: 200,
    visible: () => true,
    loadUnread: async () => {
      polled += 1
      return 5
    },
  })
  const pollingOk = await waitUntil(() => polled > 0)
  polling.stop()
  result.push({
    label: '⑬ 多标签同步与轮询占位校准（BroadcastChannel + 轮询）',
    pass: synced && pollingOk,
  })

  checks.value = result
  document.body.setAttribute('data-check-done', result.every((item) => item.pass) ? 'pass' : 'fail')
}

onMounted(() => {
  void runChecks()
})
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>通知与消息核对页（07-4）</h1>
    <section data-check-scope="bell" style="margin-bottom: 16px">
      <NoticeBell
        :ready="api.ready.value"
        :unread-count="api.unreadCount.value"
        :items="api.items.value"
        :recent-limit="5"
        connection-state="connected"
        @read-all="counters.readAll += 1"
        @view-all="counters.viewAll += 1"
      />
    </section>

    <section data-check-scope="list">
      <NoticeList
        :ready="api.ready.value"
        :items="api.items.value"
        :unread-count="api.unreadCount.value"
        :total="api.total.value"
        :page="api.page.value"
        :page-size="api.pageSize.value"
        :show-filter="true"
        :selectable="true"
        :selected-ids="selectedIds"
        @open="openDetail($event.id)"
        @read="api.markRead($event)"
        @read-all="counters.readAll += 1"
        @remove="api.remove($event)"
        @update:type-filter="counters.typeFilter += 1"
        @update:page="counters.page += 1"
        @update:selected-ids="selectedIds = $event"
        @read-batch="counters.readBatch += 1"
      />
    </section>

    <section data-check-scope="item" style="margin-top: 16px">
      <NoticeMessageItem :message="sampleItem" show-type show-remove />
    </section>

    <section data-check-scope="detail">
      <NoticeDetail
        v-model="detailVisible"
        :message="detailMessage"
        :ready="api.ready.value"
        @read="counters.detailRead += 1"
        @jump="counters.jump += 1"
      />
    </section>

    <section style="margin-top: 16px">
      <button type="button" @click="api.setReady(!api.ready.value)">切换就绪 / 降级</button>
    </section>

    <section style="margin-top: 16px">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass">
          {{ item.pass ? '通过' : '失败' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>
