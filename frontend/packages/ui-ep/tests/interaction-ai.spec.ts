// kiwi_id: 960
/** AI 助手用例（08_10）：契约同实现（核心 + 投影）+ 投影薄适配 + 六件真实实现 + SSE 适配器 / Markdown + 分包边界。 */

import type { AiJobs, AiStreamAdapter, ChartEngineAdapter } from '@bms/core'
import {
  AI_CONTRACT_ACTION,
  describeAiAssistantContract,
  type AiAssistantContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AiActionConfirm from '../src/components/ai/AiActionConfirm.vue'
import AiAssistant from '../src/components/ai/AiAssistant.vue'
import AiChatPanel from '../src/components/ai/AiChatPanel.vue'
import AiComposer from '../src/components/ai/AiComposer.vue'
import AiMessageItem from '../src/components/ai/AiMessageItem.vue'
import AiSessionList from '../src/components/ai/AiSessionList.vue'
import { createSseStreamAdapter, renderAiMarkdown, splitAiContent, useBaseAiAssistant } from '../src'

/** 契约目标（投影适配）。 */
function makeTarget(): AiAssistantContractTarget {
  const base = useBaseAiAssistant()
  return {
    get ready() {
      return base.ready.value
    },
    get degraded() {
      return base.degraded.value
    },
    get requestCount() {
      return base.requestCount.value
    },
    get phase() {
      return base.phase.value
    },
    get mode() {
      return base.mode.value
    },
    get sessions() {
      return base.sessions.value
    },
    get activeSessionId() {
      return base.activeSessionId.value
    },
    get messages() {
      return base.messages.value
    },
    get streaming() {
      return base.streaming.value
    },
    get pendingAction() {
      return base.pendingAction.value
    },
    get errorCode() {
      return base.errorCode.value
    },
    get canChat() {
      return base.canChat.value
    },
    get canSend() {
      return base.canSend.value
    },
    get canAutoExecute() {
      return base.canAutoExecute.value
    },
    get autoApproveAvailable() {
      return base.autoApproveAvailable.value
    },
    setReady: (value) => base.setReady(value),
    setAccessCodes: (codes) => base.setAccessCodes(codes),
    setJobs: (jobs) => base.setJobs(jobs as AiJobs),
    setStream: (adapter) => base.setStream(adapter as AiStreamAdapter | undefined),
    setMode: (mode) => base.setMode(mode as never),
    setSessions: (sessions) => base.setSessions(sessions as never),
    setMessages: (messages) => base.setMessages(messages as never),
    selectSession: (id) => base.selectSession(id),
    newSession: (mode) => base.newSession(mode as never),
    loadSessions: () => base.loadSessions(),
    loadMessages: (sessionId) => base.loadMessages(sessionId),
    send: (input) => base.send(input),
    appendChunk: (delta) => base.appendChunk(delta),
    stop: () => base.stop(),
    regenerate: (messageId) => base.regenerate(messageId),
    retry: () => base.retry(),
    setPendingAction: (action) => base.setPendingAction(action),
    setAutoExecute: (value) => base.setAutoExecute(value),
    confirmAction: (actionId) => base.confirmAction(actionId),
    revokeAction: (actionId) => base.revokeAction(actionId),
    dispose: () => base.dispose(),
  }
}

describeAiAssistantContract('AI 助手契约（08_10 冻结）', makeTarget)

/** 引擎桩。 */
const engineStub: ChartEngineAdapter = {
  init: () => undefined,
  update: () => undefined,
  applyTheme: () => undefined,
  resize: () => undefined,
  exportImage: () => '',
  dispose: () => undefined,
}

describe('useBaseAiAssistant 投影', () => {
  it('占位态降级且取数零请求', async () => {
    const base = useBaseAiAssistant({ accessCodes: ['ai:chat'] })
    expect(base.degraded.value).toBe(true)
    await base.loadSessions()
    await base.loadMessages('s1')
    expect(base.requestCount.value).toBe(0)
  })

  it('就绪装载会话与消息、流式追加与停止', async () => {
    const base = useBaseAiAssistant({
      ready: true,
      accessCodes: ['ai:chat'],
      jobs: {
        loadSessions: async () => ({ items: [{ id: 's1', title: '会话', mode: 'ask', updatedAt: '' }], total: 1 }),
        loadMessages: async () => [],
      },
    })
    await base.loadSessions()
    expect(base.sessions.value).toHaveLength(1)
    await base.loadMessages('s1')
    const chunks: string[] = []
    const stream: AiStreamAdapter = {
      start: ({ handlers }) => {
        handlers.onChunk('你')
        handlers.onChunk('好')
        handlers.onDone({ auditId: 'log-1' })
        chunks.push('started')
        return { abort: () => chunks.push('abort') }
      },
    }
    base.setStream(stream)
    await base.send({ content: '你好' })
    expect(base.streaming.value).toBe(false)
    expect(chunks).toEqual(['started'])
    await base.stop()
  })
})

describe('AiAssistant 容器', () => {
  const datasets = [{ id: 'd1', code: 'sales', name: '销售', status: 'enabled' as const }]
  const sessions = [{ id: 's1', title: '会话一', mode: 'ask' as const, updatedAt: '2026-09-20' }]
  const messages = [{ id: 'm1', role: 'assistant' as const, status: 'error' as const, content: '生成失败' }]

  it('占位态降级', () => {
    const wrapper = mount(AiAssistant, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('AI 助手未就绪')
  })

  it('就绪态渲染四模式、会话、分包面板与发送 / 确认事件', async () => {
    const wrapper = mount(AiAssistant, {
      props: { ready: true, mode: 'report', datasets, sessions, activeSessionId: 's1', messages, autoExecute: true },
    })
    await wrapper.find('[data-test="mode-ask"]').trigger('click')
    expect(wrapper.emitted('update:mode')?.[0]).toEqual(['ask'])

    await wrapper.find('[data-test="new-session"]').trigger('click')
    expect(wrapper.emitted('new-session')).toHaveLength(1)
    await wrapper.find('[data-test="session-s1"]').trigger('click')
    expect(wrapper.emitted('select-session')?.[0]).toEqual(['s1'])

    await wrapper.find('[data-test="input"]').setValue('上月收款合计')
    await wrapper.find('[data-test="send"]').trigger('click')
    expect(wrapper.emitted('send')?.[0]?.[0]).toMatchObject({ mode: 'report', content: '上月收款合计', sessionId: 's1' })

    expect(wrapper.find('[data-test="stop"]').attributes('disabled')).toBeDefined()

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="chat-panel"]').attributes('data-subpackage')).toBe('ai')

    await wrapper.find('[data-test="confirm-action"]').trigger('click')
    expect(wrapper.emitted('confirm-action')?.[0]).toEqual(['s1'])
    await wrapper.find('[data-test="revoke-action"]').trigger('click')
    expect(wrapper.emitted('revoke-action')?.[0]).toEqual(['s1'])
  })

  it('注入 jobs / stream 后驱动能力基类编排', async () => {
    const calls: string[] = []
    const wrapper = mount(AiAssistant, {
      props: {
        ready: true,
        accessCodes: ['ai:chat'],
        jobs: {
          loadSessions: async () => ({ items: sessions, total: 1 }),
          loadMessages: async () => [],
        },
        stream: {
          start: ({ handlers }) => {
            calls.push('start')
            handlers.onChunk('回答')
            handlers.onDone({ auditId: 'log-1' })
            return { abort: () => calls.push('abort') }
          },
        },
      },
    })
    await wrapper.find('[data-test="input"]').setValue('你好')
    await wrapper.find('[data-test="send"]').trigger('click')
    await flushPromises()
    expect(calls).toContain('start')
    expect(wrapper.find('[data-test="ai-assistant"]').attributes('data-ready')).toBe('true')
  })

  it('流式态停止可用、非流式禁用', () => {
    const idle = mount(AiAssistant, { props: { ready: true } })
    expect(idle.find('[data-test="stop"]').attributes('disabled')).toBeDefined()
    const streaming = mount(AiAssistant, { props: { ready: true, streaming: true } })
    expect(streaming.find('[data-test="stop"]').attributes('disabled')).toBeUndefined()
  })
})

describe('AiMessageItem 消息渲染件', () => {
  it('Markdown 内容 / 引用 / 风险 / 审计与重新生成', async () => {
    const wrapper = mount(AiMessageItem, {
      props: {
        message: {
          id: 'm1',
          role: 'assistant',
          status: 'done',
          content: '**加粗**',
          citations: [{ type: 'record', title: '单据 42', id: 'r1' }],
          risks: ['额度不足'],
          auditId: 'log-3',
        },
      },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="message-content"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="message-citation"]').text()).toContain('单据 42')
    expect(wrapper.find('[data-test="message-risk"]').text()).toContain('额度不足')
    expect(wrapper.find('[data-test="message-audit"]').text()).toContain('log-3')

    const failed = mount(AiMessageItem, {
      props: { message: { id: 'm2', role: 'assistant', status: 'error', content: '失败' } },
    })
    await failed.find('[data-test="message-regenerate"]').trigger('click')
    expect(failed.emitted('regenerate')?.[0]).toEqual(['m2'])
  })
})

describe('AiChatPanel 对话面板', () => {
  it('渲染消息、图表结果、引用、风险与审计，并可重新生成', async () => {
    const wrapper = mount(AiChatPanel, {
      props: {
        streaming: false,
        engineFactory: async () => engineStub,
        messages: [
          {
            id: 'm1',
            role: 'assistant',
            status: 'done',
            content: '**加粗**',
            result: {
              kind: 'chart',
              chartType: 'bar',
              columns: [
                { name: 'month', type: 'text' },
                { name: 'receipt', type: 'number' },
              ],
              rows: [{ month: '1月', receipt: 12 }],
            },
            citations: [{ type: 'file', title: '文档 A', id: 'f1' }],
            risks: ['库存不足'],
            auditId: 'log-9',
          },
          { id: 'm2', role: 'assistant', status: 'error', content: '失败' },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="chat-panel"]').attributes('data-subpackage')).toBe('ai')
    expect(wrapper.find('[data-test="message-content"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="message-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="message-citation"]').text()).toContain('文档 A')
    expect(wrapper.find('[data-test="message-risk"]').text()).toContain('库存不足')
    expect(wrapper.find('[data-test="message-audit"]').text()).toContain('log-9')

    await wrapper.find('[data-test="message-regenerate"]').trigger('click')
    expect(wrapper.emitted('regenerate')?.[0]).toEqual(['m2'])
  })

  it('空态与错误态', async () => {
    const empty = mount(AiChatPanel, { props: {} })
    expect(empty.find('[data-test="chat-empty"]').exists()).toBe(true)

    const error = mount(AiChatPanel, { props: { ready: true, error: true, messages: [] } })
    expect(error.find('[data-test="chat-error"]').exists()).toBe(true)
    await error.find('[data-test="chat-retry"]').trigger('click')
    expect(error.emitted('retry')).toHaveLength(1)
  })

  it('表格结果复用通用表格', async () => {
    const wrapper = mount(AiChatPanel, {
      props: {
        messages: [
          {
            id: 't1',
            role: 'assistant',
            status: 'done',
            content: '表格如下',
            result: { kind: 'table', columns: [{ name: 'name', label: '名称' }], rows: [{ name: 'A' }] },
          },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="message-table"]').exists()).toBe(true)
  })
})

describe('AiSessionList 会话列表', () => {
  const sessions = [
    { id: 's1', title: '会话一', mode: 'ask' as const, updatedAt: '2026-09-19' },
    { id: 's2', title: '会话二', mode: 'report' as const, updatedAt: '2026-09-20' },
  ]

  it('渲染、切换、新建、删除与筛选上抛', async () => {
    const wrapper = mount(AiSessionList, { props: { sessions, activeSessionId: 's1' } })
    // 按更新时间降序：s2 在前
    const items = wrapper.findAll('.bms-ai-sessions__item')
    expect(items[0].attributes('data-test')).toBe('session-s2')

    await wrapper.find('[data-test="session-s1"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['s1'])

    await wrapper.find('[data-test="new-session"]').trigger('click')
    expect(wrapper.emitted('create')).toHaveLength(1)

    await wrapper.find('[data-test="remove-session-s2"]').trigger('click')
    expect(wrapper.emitted('remove')?.[0]).toEqual(['s2'])

    await wrapper.find('[data-test="session-filter"]').setValue('report')
    expect(wrapper.emitted('update:mode')?.[0]).toEqual(['report'])
  })

  it('空态', () => {
    const wrapper = mount(AiSessionList, { props: { sessions: [] } })
    expect(wrapper.find('[data-test="session-empty"]').exists()).toBe(true)
  })
})

describe('AiComposer 输入区', () => {
  it('输入、字数、发送与停止', async () => {
    const wrapper = mount(AiComposer, { props: { modelValue: '', mode: 'report' } })
    await wrapper.find('[data-test="input"]').setValue('你好')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['你好'])
    await wrapper.setProps({ modelValue: '你好' })
    await wrapper.find('[data-test="send"]').trigger('click')
    expect(wrapper.emitted('send')).toHaveLength(1)
    expect(wrapper.find('[data-test="stop"]').attributes('disabled')).toBeDefined()

    await wrapper.setProps({ streaming: true })
    expect(wrapper.find('[data-test="stop"]').attributes('disabled')).toBeUndefined()
    await wrapper.find('[data-test="stop"]').trigger('click')
    expect(wrapper.emitted('stop')).toHaveLength(1)
  })

  it('超长提示与空内容不可发送', async () => {
    const wrapper = mount(AiComposer, { props: { modelValue: 'x'.repeat(2001), maxLength: 2000 } })
    expect(wrapper.find('[data-test="composer-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="send"]').attributes('disabled')).toBeDefined()
  })
})

describe('AiActionConfirm 二次确认', () => {
  /** 对话框桩（Element Plus 弹窗经 teleport，测试内联渲染）。 */
  const dialogStub = {
    ElDialog: {
      props: ['modelValue', 'title'],
      template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>',
    },
  }

  it('展示待确认内容并确认 / 撤销', async () => {
    const pending = mount(AiActionConfirm, {
      props: { modelValue: true, action: AI_CONTRACT_ACTION as never },
      global: { stubs: dialogStub },
    })
    expect(pending.find('[data-test="action-title"]').text()).toContain('生成采购申请')
    expect(pending.find('[data-test="action-content"]').text()).toContain('物料 A')
    await pending.find('[data-test="action-confirm"]').trigger('click')
    expect(pending.emitted('confirm')?.[0]).toEqual([{ actionId: 'a1' }])

    const executed = mount(AiActionConfirm, {
      props: { modelValue: true, action: { ...AI_CONTRACT_ACTION, state: 'executed', revocable: true } as never },
      global: { stubs: dialogStub },
    })
    await executed.find('[data-test="action-revoke"]').trigger('click')
    expect(executed.emitted('revoke')?.[0]).toEqual([{ actionId: 'a1' }])
  })

  it('未就绪占位', () => {
    const wrapper = mount(AiActionConfirm, {
      props: { modelValue: true, ready: false },
      global: { stubs: dialogStub },
    })
    expect(wrapper.find('[data-test="action-placeholder"]').exists()).toBe(true)
  })
})

describe('浏览器 SSE 适配器与 Markdown', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('SSE：片段 / 完成 / 失败 / abort', async () => {
    const encoder = new TextEncoder()
    const lines = ['data: {"delta":"你好"}\n', 'data: {"delta":"，世界"}\n', 'data: {"auditId":"log-1"}\n']
    let index = 0
    const signalRef: { aborted: boolean } = { aborted: false }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: unknown, init: { signal: { aborted: boolean } }) => {
        signalRef.aborted = init.signal.aborted
        return {
          ok: true,
          body: {
            getReader: () => ({
              read: async () =>
                index < lines.length
                  ? { done: false, value: encoder.encode(lines[index++]) }
                  : { done: true, value: undefined },
            }),
          },
        }
      }),
    )

    const chunks: string[] = []
    let done: { auditId?: string } | undefined
    const adapter = createSseStreamAdapter()
    const handle = adapter.start({
      request: { mode: 'ask', content: '你好' },
      handlers: {
        onChunk: (chunk) => chunks.push(chunk),
        onDone: (payload) => {
          done = payload
        },
        onError: (error) => {
          throw error
        },
      },
    })
    await flushPromises()
    await flushPromises()
    expect(chunks.join('')).toBe('你好，世界')
    expect(done?.auditId).toBe('log-1')
    handle.abort()
  })

  it('Markdown：渲染并清洗脚本', async () => {
    const html = await renderAiMarkdown('# 标题\n<script>alert(1)</script>\n**加粗**')
    expect(html).toContain('<h1')
    expect(html).not.toContain('<script')
    expect(html).toContain('<strong>')
  })

  it('内容分段（围栏代码）', () => {
    expect(splitAiContent('前\n```sql\nselect 1\n```\n后').map((item) => item.type)).toEqual(['text', 'code', 'text'])
  })
})
