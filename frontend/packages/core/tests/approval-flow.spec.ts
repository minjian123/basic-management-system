/** 审批流编排用例（`08-8-1`）：占位零请求 / 并行取数单失败 / 会签与进度 / 幂等提交与防重复 / 错误码处置 / 只读图三级降级 / 只读态。 */

import { describe, expect, it } from 'vitest'

import {
  APPROVAL_PLACEHOLDER_TEXT,
  BaseAccess,
  BaseApprovalFlow,
  type ApprovalInstanceInput,
  type ApprovalJobs,
  type ApprovalSubmitInput,
} from '../src'

/** 具体审批流编排件（可实例化）。 */
class ApprovalFlowState extends BaseApprovalFlow {}

/** 权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 实例装载输入夹具。 */
const INSTANCE_INPUT: ApprovalInstanceInput = {
  id: 'wf-1',
  status: 'running',
  currentNodeId: 'n2',
  bpmnXml: '<bpmn:definitions />',
  nodes: [
    { nodeId: 'n1', name: '发起', status: 'done' },
    {
      nodeId: 'n2',
      name: '主管审批',
      status: 'active',
      signed: true,
      signedDone: 1,
      signedTotal: 2,
      assignees: [
        { id: 'u1', name: '张三' },
        { id: 'u2', name: '李四' },
      ],
    },
    { nodeId: 'n3', name: '财务审批', status: 'pending' },
  ],
}

/** 构造「已就绪且已装载」的编排实例。 */
function readyFlow(jobs: ApprovalJobs = {}): BaseApprovalFlow {
  const flow = new ApprovalFlowState()
  flow.setJobs(jobs)
  flow.setReady(true)
  flow.applyInstance(INSTANCE_INPUT)
  flow.applyRecords([
    { id: 'r1', nodeId: 'n1', nodeName: '发起', assigneeName: '王五', action: 'approve', comment: '同意' },
  ])
  flow.applyTask({ taskId: 'task-1', nodeId: 'n2', nodeName: '主管审批' })
  flow.withdrawable = true
  const access = new DemoAccess()
  access.setCodes(['wf:approve'])
  flow.setAccess(access)
  return flow
}

describe('占位语义', () => {
  it('未就绪：降级且禁用，取数与提交零请求', async () => {
    const flow = new ApprovalFlowState()
    flow.setJobs({
      loadInstance: async () => INSTANCE_INPUT,
      submit: async () => ({ recordVersion: 1 }),
    })
    expect(flow.ready).toBe(false)
    expect(flow.degraded).toBe(true)
    expect(flow.disabled).toBe(true)
    expect(flow.errorMessage).toBe('')
    await flow.load()
    expect(flow.requestCount).toBe(0)
    await flow.submit('approve', { comment: '同意' })
    expect(flow.requestCount).toBe(0)
  })

  it('就绪但未注入处理函数：不请求、不再降级', async () => {
    const flow = new ApprovalFlowState()
    flow.setReady(true)
    expect(flow.degraded).toBe(false)
    expect(flow.disabled).toBe(false)
    await flow.load()
    expect(flow.requestCount).toBe(0)
    await expect(flow.submit('approve', { comment: '同意' })).resolves.toBeUndefined()
    expect(flow.errorMessage).toBe(APPROVAL_PLACEHOLDER_TEXT)
  })
})

describe('并行取数与分部结算', () => {
  it('两侧成功：请求计数按实际发起数累加', async () => {
    const flow = readyFlow({
      loadInstance: async () => INSTANCE_INPUT,
      loadRecords: async () => [{ id: 'r1', nodeId: 'n1', action: 'approve' }],
    })
    await expect(flow.load()).resolves.toBe(true)
    expect(flow.requestCount).toBe(2)
    expect(flow.instanceState).toBe('ready')
    expect(flow.recordsState).toBe('ready')
    expect(flow.records).toHaveLength(1)
  })

  it('单失败不整体报错：记录失败时进度仍可读', async () => {
    const flow = readyFlow({
      loadInstance: async () => INSTANCE_INPUT,
      loadRecords: async () => {
        throw new Error('记录接口异常')
      },
    })
    await expect(flow.load()).resolves.toBe(false)
    expect(flow.instanceState).toBe('ready')
    expect(flow.recordsState).toBe('error')
    expect(flow.progress.total).toBe(3)
    expect(flow.pendingRefresh).toBe(true)
    expect(flow.phase).toBe('done')
  })

  it('空集合置空态', async () => {
    const flow = readyFlow({ loadRecords: async () => [] })
    await flow.load()
    expect(flow.recordsState).toBe('empty')
  })
})

describe('进度与会签', () => {
  it('进度摘要与当前节点', () => {
    const flow = readyFlow()
    expect(flow.progress).toEqual({ done: 1, total: 3, activeName: '主管审批' })
  })

  it('只读判定：实例结束为只读', () => {
    const flow = readyFlow()
    expect(flow.readonly).toBe(false)
    flow.applyInstance({ ...INSTANCE_INPUT, status: 'finished' })
    expect(flow.readonly).toBe(true)
    expect(flow.actions.approve).toBe(false)
  })
})

describe('提交与幂等', () => {
  it('提交载荷携带内容派生幂等键，提交后刷新', async () => {
    const seen: string[] = []
    const flow = readyFlow({
      loadInstance: async () => INSTANCE_INPUT,
      loadRecords: async () => [],
      submit: async (payload) => {
        seen.push(payload.idempotencyKey)
        return { recordVersion: 3 }
      },
    })
    const expected = flow.idempotencyKey('approve', '同意')
    await flow.submit('approve', { comment: '同意' })
    expect(seen).toEqual([expected])
    expect(flow.phase).toBe('done')
    // 提交 1 次 + 成功后刷新实例 1 次（记录取数返回空亦计 1 次）。
    expect(flow.requestCount).toBe(3)
  })

  it('重复提交按成功处理（60005）', async () => {
    const flow = readyFlow({
      submit: async () => {
        throw Object.assign(new Error('重复提交被拦截'), { code: 60005 })
      },
    })
    await flow.submit('approve', { comment: '同意' })
    expect(flow.phase).toBe('done')
    expect(flow.errorHandling?.handling).toBe('duplicated')
    expect(flow.readonly).toBe(false)
  })

  it('越权（60003）失败并刷新、可重试', async () => {
    let attempt = 0
    const flow = readyFlow({
      loadInstance: async () => INSTANCE_INPUT,
      submit: async () => {
        attempt += 1
        if (attempt === 1) {
          throw Object.assign(new Error('非当前审批人'), { code: 60003 })
        }
        return { recordVersion: 5 }
      },
    })
    await flow.submit('approve', { comment: '同意' })
    expect(flow.phase).toBe('failed')
    expect(flow.errorHandling?.handling).toBe('denied')
    // 提交 1 次 + 失败后按错误码刷新实例 1 次。
    expect(flow.requestCount).toBe(2)

    await expect(flow.retry()).resolves.toMatchObject({ recordVersion: 5 })
    expect(flow.phase).toBe('done')
  })

  it('引擎异常（60009）置只读', async () => {
    const flow = readyFlow({
      submit: async () => {
        throw Object.assign(new Error('引擎异常'), { code: 60009 })
      },
    })
    await flow.submit('approve', { comment: '同意' })
    expect(flow.readonly).toBe(true)
    expect(flow.actions.approve).toBe(false)
  })

  it('校验不通过时不请求（驳回意见必填）', async () => {
    const flow = readyFlow({ submit: async () => ({ recordVersion: 1 }) })
    const before = flow.requestCount
    await flow.submit('reject', { comment: '' })
    expect(flow.requestCount).toBe(before)
    expect(flow.errorMessage).toContain('意见')
  })

  it('进行中重复提交不动作', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    let calls = 0
    const flow = readyFlow({
      submit: async () => {
        calls += 1
        await gate
        return { recordVersion: 1 }
      },
    })
    const pending = flow.submit('approve', { comment: '同意' })
    expect(flow.busy).toBe(true)
    await expect(flow.submit('approve', { comment: '同意' })).resolves.toBeUndefined()
    release()
    await pending
    expect(calls).toBe(1)
  })

  it('无权（缺 wf:approve）不可提交', async () => {
    const flow = readyFlow({ submit: async () => ({ recordVersion: 1 }) })
    const access = new DemoAccess()
    access.setCodes([])
    flow.setAccess(access)
    const before = flow.requestCount
    await flow.submit('approve', { comment: '同意' })
    expect(flow.requestCount).toBe(before)
  })
})

describe('只读图', () => {
  it('形态判定与失败降级', async () => {
    const flow = readyFlow()
    expect(flow.diagramMode).toBe('xml')

    flow.applyInstance({ ...INSTANCE_INPUT, bpmnXml: '' })
    expect(flow.diagramMode).toBe('none')

    flow.setJobs({ loadDiagramUrl: async () => ({ url: 'https://example.test/a.png', expiresAt: Date.now() + 1000 }) })
    await expect(flow.loadDiagramImage()).resolves.toBe('https://example.test/a.png')
    expect(flow.diagramMode).toBe('image')

    flow.markDiagramFailed()
    expect(flow.diagramMode).toBe('failed')
  })

  it('经预签名能力取图（未注入处理函数时）', async () => {
    const flow = readyFlow()
    flow.applyInstance({ ...INSTANCE_INPUT, bpmnXml: '' })
    const presigned = {
      url: undefined as string | undefined,
      expiresAt: 0,
      fetcher: async () => ({ url: 'https://example.test/p.png', expiresAt: Date.now() + 1000 }),
      get: async () => 'https://example.test/p.png',
      refresh: () => undefined,
      isExpired: () => false,
    }
    flow.setPresigned(presigned as never)
    await expect(flow.loadDiagramImage()).resolves.toBe('https://example.test/p.png')
    expect(flow.diagramMode).toBe('image')
  })

  it('未注入任何取址时不产生请求', async () => {
    const flow = readyFlow()
    flow.applyInstance({ ...INSTANCE_INPUT, bpmnXml: '' })
    const before = flow.requestCount
    await expect(flow.loadDiagramImage()).resolves.toBeUndefined()
    expect(flow.requestCount).toBe(before)
  })
})

describe('实例切换与重置', () => {
  it('切换实例标识清空装载结果', () => {
    const flow = readyFlow()
    flow.setInstanceId('wf-2')
    expect(flow.instance).toBeUndefined()
    expect(flow.records).toEqual([])
    expect(flow.instanceState).toBe('idle')
    expect(flow.phase).toBe('idle')
  })

  it('重置清错误与重试入参（保留装载结果）', async () => {
    const flow = readyFlow({
      submit: async () => {
        throw Object.assign(new Error('越权'), { code: 60003 })
      },
    })
    await flow.submit('approve', { comment: '同意' })
    expect(flow.phase).toBe('failed')
    flow.reset()
    expect(flow.phase).toBe('idle')
    expect(flow.errorHandling).toBeUndefined()
    expect(await flow.retry()).toBeUndefined()
    expect(flow.instance).toBeDefined()
  })

  it('提交入参类型承载意见与目标', () => {
    const input: ApprovalSubmitInput = { comment: '不通过', target: 'n1' }
    expect(input).toEqual({ comment: '不通过', target: 'n1' })
  })
})
