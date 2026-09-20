// kiwi_id: 960
/** AI 对话领域纯函数用例（08_10）：归一 / 流式状态机 / 会话排序筛选 / 结果与引用 / 二次确认与撤销 / 错误码 / 内容分段。 */

import { describe, expect, it } from 'vitest'

import {
  appendStreamChunk,
  applyActionConfirm,
  applyActionExecute,
  applyActionFail,
  applyActionRevoke,
  autoApproveAvailable,
  canAutoExecute,
  canRegenerate,
  canRevokeAction,
  canSend,
  canStop,
  citationTypeLabel,
  countAiCodePoints,
  deriveAiKey,
  deriveSessionTitle,
  failMessage,
  filterSessions,
  finishMessage,
  isAiErrorCode,
  messageStatusLabel,
  modeLabel,
  nextMessageId,
  nextSessionId,
  normalizeAiCitations,
  normalizeAiMessage,
  normalizeAiMessages,
  normalizeAiResult,
  normalizeAiResultColumns,
  normalizeAiSessions,
  normalizeAiSessionsPage,
  normalizePendingAction,
  reduceStream,
  requiresConfirm,
  resolveActionState,
  resolveAiErrorText,
  resolveAiSemantic,
  resolveRegenerateInput,
  sortSessions,
  splitContentSegments,
  startStreamMessage,
  stopMessage,
  validatePrompt,
  type AiMessage,
  type AiPendingAction,
  type AiSession,
} from '../src'

/** 待确认动作（本地强类型样例）。 */
const ACTION: AiPendingAction = {
  id: 'a1',
  title: '生成采购申请',
  summary: '按缺口生成采购申请',
  content: '物料 A × 100',
  state: 'pending',
  confirmable: true,
  revocable: true,
}

describe('AI 对话领域纯函数', () => {
  it('模式 / 状态 / 语义 / 引用标签', () => {
    expect(modeLabel('report')).toBe('智能问数')
    expect(modeLabel('approval')).toBe('审批辅助')
    expect(modeLabel('doc_qa')).toBe('文档问答')
    expect(modeLabel('ask')).toBe('通用对话')
    expect(messageStatusLabel('streaming')).toBe('生成中')
    expect(messageStatusLabel('error')).toBe('生成失败')
    expect(messageStatusLabel('stopped')).toBe('已停止')
    expect(messageStatusLabel('done')).toBe('已完成')
    expect(resolveAiSemantic('streaming')).toBe('primary')
    expect(resolveAiSemantic('error')).toBe('danger')
    expect(resolveAiSemantic('stopped')).toBe('info')
    expect(citationTypeLabel('record')).toBe('业务记录')
  })

  it('消息归一（缺 id 剔除、非白名单回退、空内容保留）', () => {
    expect(normalizeAiMessage({ role: 'user', content: 'x' })).toBeUndefined()
    expect(normalizeAiMessage({ id: 'm1' })).toMatchObject({ status: 'done', role: 'assistant', content: '' })
    expect(normalizeAiMessages([{ id: 'm1', role: 'zzz', status: 'zzz', content: '' }])[0]).toMatchObject({
      role: 'assistant',
      status: 'done',
    })
    expect(normalizeAiMessages('x')).toEqual([])
  })

  it('结果与引用归一（脏项剔除）', () => {
    expect(
      normalizeAiResult({ kind: 'chart', chartType: 'bar', columns: [{ name: 'a' }, {}], rows: [1] }),
    ).toEqual({
      kind: 'chart',
      chartType: 'bar',
      columns: [{ name: 'a' }],
      rows: [1],
    })
    expect(normalizeAiResult({ kind: 'zzz' })).toBeUndefined()
    expect(normalizeAiResultColumns([{ name: 'a', type: 'number', label: '额' }, { type: 'x' }])).toEqual([
      { name: 'a', type: 'number', label: '额' },
    ])
    expect(normalizeAiCitations([{ type: 'file', title: 'F', id: '1' }, { title: 'x' }])).toEqual([
      { type: 'file', title: 'F', id: '1' },
    ])
  })

  it('会话归一、排序与筛选', () => {
    expect(normalizeAiSessions([{ id: 's1' }])[0]).toEqual({
      id: 's1',
      title: '新会话',
      mode: 'ask',
      updatedAt: '',
    })
    expect(normalizeAiSessionsPage([{ id: 's1' }])).toEqual({
      items: [{ id: 's1', title: '新会话', mode: 'ask', updatedAt: '' }],
      total: 1,
    })
    const sessions: AiSession[] = [
      { id: 's1', title: 'A', mode: 'ask', updatedAt: '2026-09-19T00:00:00Z' },
      { id: 's2', title: 'B', mode: 'report', updatedAt: '2026-09-20T00:00:00Z' },
    ]
    expect(sortSessions(sessions).map((item) => item.id)).toEqual(['s2', 's1'])
    expect(filterSessions(sessions, { mode: 'report' }).map((item) => item.id)).toEqual(['s2'])
    expect(filterSessions(sessions, { keyword: 'A' }).map((item) => item.id)).toEqual(['s1'])
  })

  it('标识派生与标题截断', () => {
    expect(nextSessionId([{ id: 's-1', title: 't', mode: 'ask', updatedAt: '' }])).toBe('s-2')
    expect(nextMessageId([{ id: 'm-1', role: 'user', status: 'done', content: '' }])).toBe('m-2')
    expect(deriveSessionTitle('  上月   各部门收款合计  ', 5)).toBe('上月 各部…')
    expect(deriveSessionTitle('   ')).toBe('新会话')
  })

  it('流式状态机（追加 / 结束 / 失败 / 停止 / 迟到帧）', () => {
    const message = startStreamMessage({ id: 'm1', role: 'assistant' })
    expect(message.status).toBe('streaming')
    const appended = appendStreamChunk(message, '你好')
    expect(appended.content).toBe('你好')
    const done = finishMessage(appended, { auditId: 'log-1', result: { kind: 'table', rows: [] } })
    expect(done.status).toBe('done')
    expect(done.auditId).toBe('log-1')
    expect(done.result?.kind).toBe('table')
    expect(appendStreamChunk(done, '迟到').content).toBe('你好')
    expect(failMessage(message, '失败').status).toBe('error')
    expect(failMessage(message, '失败').content).toBe('失败')
    expect(stopMessage(appended)).toMatchObject({ status: 'stopped', content: '你好' })
    expect(reduceStream(message, { type: 'chunk', delta: 'x' }).content).toBe('x')
  })

  it('发送 / 停止 / 重生成判定', () => {
    expect(canSend(true, '你好', false, true)).toBe(true)
    expect(canSend(true, '', false, true)).toBe(false)
    expect(canSend(false, '你好', false, true)).toBe(false)
    expect(canSend(true, '你好', true, true)).toBe(false)
    expect(canStop(true)).toBe(true)
    const message: AiMessage = { id: 'm1', role: 'assistant', status: 'error', content: '' }
    expect(canRegenerate(message)).toBe(true)
    expect(canRegenerate({ ...message, status: 'done' })).toBe(false)
  })

  it('输入校验与码点统计', () => {
    expect(validatePrompt('你好').valid).toBe(true)
    expect(validatePrompt('  ').valid).toBe(false)
    expect(validatePrompt('x'.repeat(2001)).valid).toBe(false)
    expect(countAiCodePoints('😀a')).toBe(2)
  })

  it('二次确认与撤销状态机', () => {
    expect(requiresConfirm(ACTION)).toBe(true)
    expect(applyActionConfirm(ACTION).state).toBe('confirmed')
    const executed = applyActionExecute(ACTION, { auditId: 'log-1', revocable: true })
    expect(executed.state).toBe('executed')
    expect(executed.auditId).toBe('log-1')
    expect(canRevokeAction(executed)).toBe(true)
    expect(canRevokeAction({ ...executed, revocable: false })).toBe(false)
    expect(applyActionRevoke(executed).state).toBe('revoked')
    expect(applyActionFail(ACTION).state).toBe('failed')
    expect(resolveActionState(ACTION)).toBe('pending')
    expect(canAutoExecute(true, true)).toBe(true)
    expect(autoApproveAvailable(false, true)).toBe(false)
  })

  it('待确认动作归一', () => {
    expect(normalizePendingAction({ id: 'a1', title: 't', state: 'zzz' })?.state).toBe('pending')
    expect(normalizePendingAction({ title: 't' })).toBeUndefined()
  })

  it('错误码识别与文案', () => {
    expect(isAiErrorCode(10201)).toBe(true)
    expect(isAiErrorCode(10216)).toBe(true)
    expect(isAiErrorCode(10300)).toBe(false)
    expect(resolveAiErrorText(10201)).toBe('模型不可用或未配置')
    expect(resolveAiErrorText(99999)).toBe('AI 请求失败')
  })

  it('幂等键确定性', () => {
    expect(deriveAiKey({ a: 1, b: [2, 3] })).toBe(deriveAiKey({ b: [2, 3], a: 1 }))
    expect(deriveAiKey({ a: 1 })).toMatch(/^ai:[0-9a-f]+$/)
  })

  it('内容分段（围栏代码）', () => {
    const segments = splitContentSegments('说明\n```sql\nselect 1\n```\n结尾')
    expect(segments.map((item) => item.type)).toEqual(['text', 'code', 'text'])
    expect(segments[1]).toEqual({ type: 'code', text: 'select 1', lang: 'sql' })
  })

  it('重生成取原问题', () => {
    const messages: AiMessage[] = [
      { id: 'm1', role: 'user', status: 'done', content: '问题' },
      { id: 'm2', role: 'assistant', status: 'error', content: '' },
    ]
    expect(resolveRegenerateInput(messages, 'm2', 'ask')).toEqual({ content: '问题', mode: 'ask' })
    expect(resolveRegenerateInput(messages, 'm1')).toBeUndefined()
  })
})
