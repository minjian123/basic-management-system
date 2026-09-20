<script setup lang="ts">
// 开发态核对页（08_10）：AI 助手实例 + 12 项自检上屏（本页不进构建产物）。
import type { AiMessage, AiStreamAdapter, AiStreamHandlers } from '@bms/core'
import { AiAssistant, useBaseAiAssistant } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 种子会话。 */
const seedSessions = [
  { id: 's1', title: '上月收款合计', mode: 'ask' as const, updatedAt: '2026-09-20T10:00:00Z' },
  { id: 's2', title: '采购审批辅助', mode: 'approval' as const, updatedAt: '2026-09-19T10:00:00Z' },
]

/** 种子消息（用户 + 助手已完成）。 */
const seedMessages: AiMessage[] = [
  { id: 'm1', role: 'user', status: 'done', content: '上月各部门收款合计' },
  { id: 'm2', role: 'assistant', status: 'done', content: '共收款 **120 万**。' },
]

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])
/** 交互计数。 */
const counters = ref({ mode: 0, select: 0, create: 0, remove: 0, send: 0, retry: 0 })
/** 组件权限码（⑪ 校验门控）。 */
const accessCodes = ref<string[]>(['ai:chat'])

/** 桩流式适配器（手动派发片段 / 完成 / 失败）。 */
let handlers: AiStreamHandlers | undefined
const streamCalls: string[] = []
const stream: AiStreamAdapter = {
  start: (input) => {
    handlers = input.handlers
    streamCalls.push('start')
    return { abort: () => streamCalls.push('abort') }
  },
}

const api = useBaseAiAssistant({
  ready: false,
  accessCodes: ['ai:chat'],
  autoExecute: true,
  jobs: {
    loadSessions: async () => ({ items: seedSessions, total: 2 }),
    loadMessages: async () => seedMessages,
    confirmAction: async () => ({ revocable: true, auditId: 'log-action' }),
    revokeAction: async () => true,
  },
})
api.setStream(stream)
api.setSessions(seedSessions)
api.setMessages(seedMessages)

/**
 * 作用域内查询元素。
 *
 * @param selector 选择器。
 */
function q(selector: string): Element | null {
  return document.querySelector(`[data-check-scope="assistant"] ${selector}`)
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
 * 点击元素。
 *
 * @param selector 选择器。
 */
async function click(selector: string): Promise<void> {
  const element = q(selector)
  if (element instanceof HTMLElement) {
    element.click()
  }
  await settle()
}

/**
 * 设置输入值并派发。
 *
 * @param selector 选择器。
 * @param value 值。
 */
async function type(selector: string, value: string): Promise<void> {
  const element = q(selector)
  if (element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement) {
    element.value = value
    element.dispatchEvent(new Event('input', { bubbles: true }))
  }
  await settle()
}

/** 最近一条助手消息。 */
function lastAssistant(): AiMessage | undefined {
  return [...api.messages.value].reverse().find((message) => message.role === 'assistant')
}

/** 发送一条消息（经容器事件驱动投影）。 */
async function sendMessage(text: string): Promise<void> {
  await type('[data-test="input"]', text)
  counters.value.send += 1
  await click('[data-test="send"]')
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  await settle()

  // ① 占位降级与就绪切换
  const degraded = q('[data-test="placeholder"]') !== null
  api.setReady(true)
  await settle()
  result.push({
    label: '① 占位降级与就绪切换',
    pass: degraded && q('[data-test="ai-assistant"]')?.getAttribute('data-ready') === 'true',
  })

  // ② 四模式切换与会话列表
  await click('[data-test="mode-report"]')
  await click('[data-test="session-s2"]')
  await click('[data-test="new-session"]')
  result.push({
    label: '② 四模式切换与会话列表（切换 / 新建）',
    pass: counters.value.mode > 0 && counters.value.select > 0 && counters.value.create > 0 && q('[data-test="session-s2"]') !== null,
  })
  api.selectSession('s1')
  await settle()

  // ③ 发送消息与流式逐帧追加
  const before = api.messages.value.length
  await sendMessage('上月收款合计')
  const started = api.messages.value.length === before + 2 && api.streaming.value === true && streamCalls.includes('start')
  handlers?.onChunk('上月各部门')
  handlers?.onChunk('共收款 120 万。')
  await settle()
  result.push({
    label: '③ 发送消息（用户 + 助手）与流式逐帧追加',
    pass: started && (lastAssistant()?.content ?? '').includes('120 万'),
  })

  // ④ 停止（保留内容、stopped）与重新生成
  await click('[data-test="stop"]')
  const stopped = lastAssistant()?.status === 'stopped' && streamCalls.includes('abort')
  await api.regenerate()
  await settle()
  handlers?.onChunk('重生成内容')
  handlers?.onDone({ auditId: 'log-1' })
  await settle()
  result.push({
    label: '④ 停止（保留已接收内容）与重新生成',
    pass: stopped && lastAssistant()?.status === 'done' && lastAssistant()?.auditId === 'log-1',
  })

  // ⑤ 流式失败降级与重试
  await sendMessage('再问一次')
  handlers?.onError(new Error('模型不可用'))
  await settle()
  const failed = lastAssistant()?.status === 'error' && api.phase.value === 'error'
  await api.retry()
  await settle()
  handlers?.onChunk('重试成功')
  handlers?.onDone()
  await settle()
  result.push({
    label: '⑤ 流式失败降级（error）与重试',
    pass: failed && api.streaming.value === false && lastAssistant()?.status === 'done',
  })

  // ⑥ 问数结果图表渲染（复用 ChartRenderer）
  api.setMessages([
    {
      id: 'c1',
      role: 'assistant',
      status: 'done',
      content: '结果如下',
      result: {
        kind: 'chart',
        chartType: 'bar',
        columns: [
          { name: 'month', type: 'text' },
          { name: 'receipt', type: 'number' },
        ],
        rows: [
          { month: '1月', receipt: 120 },
          { month: '2月', receipt: 180 },
        ],
      },
    },
  ])
  await settle()
  const chartOk = await waitUntil(() => q('[data-test="message-chart"]') !== null)
  result.push({ label: '⑥ 问数结果图表渲染（复用图表卡 ChartRenderer）', pass: chartOk })

  // ⑦ 表格结果（复用通用表格）
  api.setMessages([
    {
      id: 't1',
      role: 'assistant',
      status: 'done',
      content: '表格结果',
      result: { kind: 'table', columns: [{ name: 'dept', label: '部门' }, { name: 'amount', label: '金额' }], rows: [{ dept: '销售部', amount: 120 }] },
    },
  ])
  await settle()
  result.push({ label: '⑦ 表格结果渲染（复用通用表格 DataTable）', pass: q('[data-test="message-table"]') !== null })

  // ⑧ 引用来源 / 风险提示 / 审计标识
  api.setMessages([
    {
      id: 'q1',
      role: 'assistant',
      status: 'done',
      content: '参考意见',
      citations: [{ type: 'record', title: '历史审批 42', id: 'r1' }],
      risks: ['额度不足'],
      auditId: 'log-2',
    },
  ])
  await settle()
  result.push({
    label: '⑧ 引用来源 / 风险提示 / 审计标识',
    pass:
      q('[data-test="message-citation"]')?.textContent?.includes('历史审批 42') === true &&
      q('[data-test="message-risk"]')?.textContent?.includes('额度不足') === true &&
      q('[data-test="message-audit"]')?.textContent?.includes('log-2') === true,
  })

  // ⑨ 待确认内容展示与强制二次确认
  api.setPendingAction({
    id: 'a1',
    title: '生成采购申请',
    summary: '按缺口生成采购申请',
    content: '物料 A × 100',
    state: 'pending',
    confirmable: true,
    revocable: true,
  })
  await settle()
  const confirmShown =
    document.querySelector('[data-test="action-content"]')?.textContent?.includes('物料 A') === true &&
    document.querySelector('[data-test="action-confirm"]') !== null
  await api.confirmAction('a1')
  await settle()
  result.push({
    label: '⑨ 待确认内容展示与强制二次确认',
    pass: confirmShown && api.pendingAction.value?.state === 'executed',
  })

  // ⑩ 撤销与不可撤销提示
  await api.revokeAction('a1')
  await settle()
  const revoked = api.pendingAction.value?.state === 'revoked'
  api.setPendingAction({ id: 'a2', title: '不可撤销动作', state: 'executed', confirmable: false, revocable: false })
  await api.revokeAction('a2')
  await settle()
  result.push({
    label: '⑩ 撤销与不可撤销提示（10212）',
    pass: revoked && api.errorCode.value === 10212,
  })

  // ⑪ 权限门控与自动执行开关
  accessCodes.value = []
  api.setAccessCodes([])
  await settle()
  const noPerm = api.canChat.value === false && q('[data-test="readonly-hint"]') !== null
  accessCodes.value = ['ai:chat']
  api.setAccessCodes(['ai:chat'])
  api.setAutoExecute(false)
  api.setPendingAction({ id: 'a3', title: '动作', state: 'pending', confirmable: true, revocable: false })
  await api.confirmAction('a3')
  await settle()
  result.push({
    label: '⑪ 权限门控（ai:chat）与自动执行开关（10208）',
    pass: noPerm && api.errorCode.value === 10208,
  })

  // ⑫ 分包边界
  const panelOk = await waitUntil(() => q('[data-test="chat-panel"]') !== null)
  result.push({
    label: '⑫ 对话面板独立分包（data-subpackage=ai）',
    pass: panelOk && q('[data-test="chat-panel"]')?.getAttribute('data-subpackage') === 'ai',
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
    <h1>AI 助手核对页（08-10）</h1>
    <section data-check-scope="assistant" style="height: 520px">
      <AiAssistant
        :ready="api.ready.value"
        :mode="api.mode.value"
        :sessions="api.sessions.value"
        :active-session-id="api.activeSessionId.value"
        :messages="api.messages.value"
        :streaming="api.streaming.value"
        :auto-execute="api.autoExecute.value"
        :access-codes="accessCodes"
        :pending-action="api.pendingAction.value"
        :shortcuts="['上月收款合计', '部门费用对比']"
        @update:mode="counters.mode += 1"
        @select-session="counters.select += 1"
        @new-session="counters.create += 1"
        @remove-session="counters.remove += 1"
        @send="api.send({ content: $event.content, datasetId: $event.datasetId })"
        @stop="api.stop()"
        @regenerate="api.regenerate($event)"
        @retry="counters.retry += 1"
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
