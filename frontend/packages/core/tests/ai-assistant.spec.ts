// kiwi_id: 960
/** AI 助手能力基类用例（08_10）：契约同实现（核心 + 投影）+ 身份依赖 + 占位门控 + 选项源接入。 */

import { BaseAccess, BaseAiAssistant, BaseOptionSource } from '@bms/core'
import { AI_CONTRACT_ACTION, describeAiAssistantContract, type AiAssistantContractTarget } from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

/** 具体权限上下文。 */
class DemoAccess extends BaseAccess {}

/** 具体选项源（可实例化）。 */
class OptionSourceState extends BaseOptionSource {}

/** 具体 AI 助手（可实例化）。 */
class AiState extends BaseAiAssistant {}

/** 契约目标（基类实例适配）。 */
function makeTarget(): AiAssistantContractTarget {
  const base = new AiState()
  return {
    get ready() {
      return base.ready
    },
    get degraded() {
      return base.degraded
    },
    get requestCount() {
      return base.requestCount
    },
    get phase() {
      return base.phase
    },
    get mode() {
      return base.mode
    },
    get sessions() {
      return base.sessions
    },
    get activeSessionId() {
      return base.activeSessionId
    },
    get messages() {
      return base.messages
    },
    get streaming() {
      return base.streaming
    },
    get pendingAction() {
      return base.pendingAction
    },
    get errorCode() {
      return base.errorCode
    },
    get canChat() {
      return base.canChat
    },
    get canSend() {
      return base.canSend
    },
    get canAutoExecute() {
      return base.canAutoExecute
    },
    get autoApproveAvailable() {
      return base.autoApproveAvailable
    },
    setReady: (value) => base.setReady(value),
    setAccessCodes: (codes) => {
      const access = new DemoAccess()
      access.setCodes(codes)
      base.setAccess(access)
    },
    setJobs: (jobs) => base.setJobs(jobs),
    setStream: (adapter) => base.setStream(adapter),
    setMode: (mode) => base.setMode(mode),
    setSessions: (sessions) => base.setSessions(sessions),
    setMessages: (messages) => base.setMessages(messages),
    selectSession: (id) => base.selectSession(id),
    newSession: (mode) => base.newSession(mode as AiState['mode'] | undefined),
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

describe('AI 助手能力基类身份与门控', () => {
  it('能力键与依赖登记', () => {
    const base = new AiState()
    expect(base.identifier).toBe('ai-assistant')
    expect(base.depends).toEqual(['placeholder-state', 'access', 'notice', 'data-state', 'option-source', 'async-task'])
  })

  it('未注入权限上下文视为持对话权限、非管理权限', () => {
    const base = new AiState()
    expect(base.canChat).toBe(true)
    expect(base.canManage).toBe(false)
  })

  it('持 ai:manage 时可查全量审计', () => {
    const base = new AiState()
    const access = new DemoAccess()
    access.setCodes(['ai:chat', 'ai:manage'])
    base.setAccess(access)
    expect(base.canChat).toBe(true)
    expect(base.canManage).toBe(true)
  })

  it('自动审批依赖自动执行', () => {
    const base = new AiState()
    base.setAutoExecute(false)
    base.setAutoApprove(true)
    expect(base.autoApproveAvailable).toBe(false)
    base.setAutoExecute(true)
    expect(base.autoApproveAvailable).toBe(true)
  })

  it('数据集选项经选项源加载（未注入加载器零动作）', async () => {
    const base = new AiState()
    const source = new OptionSourceState()
    base.setOptionSource(source)
    await base.refreshDatasets()
    expect(source.options).toEqual([])
    source.loader = async () => [{ value: 'd1', label: '销售' }]
    await base.refreshDatasets()
    expect(source.options).toHaveLength(1)
  })

  it('待确认动作可外部注入与状态查询', () => {
    const base = new AiState()
    base.setPendingAction(AI_CONTRACT_ACTION)
    expect(base.pendingAction?.id).toBe('a1')
    expect(base.pendingAction?.state).toBe('pending')
  })
})
