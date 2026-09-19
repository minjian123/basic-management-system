/** 审批流领域纯函数用例（`08-8-1`）：归一 / 会签聚合 / 进度摘要 / 分支降级 / 时间线 / 意见与动作校验 / 幂等键 / 只读与图形态 / 错误码处置。 */

import { describe, expect, it } from 'vitest'

import {
  APPROVAL_COMMENT_MAX,
  APPROVAL_DIAGRAM_FALLBACK_TEXT,
  APPROVAL_ERROR_HANDLERS,
  APPROVAL_UNGROUPED,
  countCodePoints,
  deriveApprovalKey,
  foldComment,
  groupRecordsByNode,
  normalizeInstance,
  normalizeRecord,
  normalizeTask,
  resolveActiveNodeIndex,
  resolveApprovalActions,
  resolveDiagramMode,
  resolveErrorHandling,
  resolveProgressSummary,
  resolveReadonlyInstance,
  resolveTimelineOrderRecords,
  resolveVisibleNodes,
  signProgress,
  validateAction,
  validateComment,
  type ApprovalInstance,
  type ApprovalRecord,
} from '../src'

/** 实例夹具：n1 已完成 / n2 会签进行中 / n3 未走。 */
const INSTANCE: ApprovalInstance = normalizeInstance({
  id: 'wf-1',
  status: 'running',
  currentNodeId: 'n2',
  bpmnXml: '<definitions />',
  nodes: [
    { nodeId: 'n1', name: '发起', status: 'done', time: '2026-09-19T09:00:00Z' },
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
})

/** 记录夹具。 */
const RECORDS: ApprovalRecord[] = [
  normalizeRecord({
    id: 'r1',
    nodeId: 'n1',
    nodeName: '发起',
    assigneeName: '王五',
    action: 'approve',
    comment: '同意',
    createdAt: '2026-09-19T09:00:00Z',
  }),
  normalizeRecord({
    id: 'r2',
    nodeId: 'n2',
    nodeName: '主管审批',
    assigneeName: '张三',
    action: 'comment',
    comment: '请补充附件',
    createdAt: '2026-09-19T10:00:00Z',
  }),
  normalizeRecord({
    id: 'r3',
    assigneeName: '无节点人',
    action: 'comment',
    createdAt: '2026-09-19T11:00:00Z',
  }),
]

describe('归一', () => {
  it('运行态不出现 undefined：状态 / 集合 / 文本字段补齐确定值', () => {
    const instance = normalizeInstance({ id: 'x' })
    expect(instance.status).toBe('running')
    expect(instance.nodes).toEqual([])
    expect(instance.bpmnXml).toBe('')

    const record = normalizeRecord({ id: 'r' })
    expect(record.action).toBe('comment')
    expect(record.comment).toBe('')
    expect(record.attachments).toEqual([])
    expect(record.nodeId).toBe('')
  })

  it('待办无任务标识返回 undefined，有则补齐集合', () => {
    expect(normalizeTask(undefined)).toBeUndefined()
    expect(normalizeTask({ nodeId: 'n1' })).toBeUndefined()
    expect(normalizeTask({ taskId: 't1', nodeId: 'n1', signed: true })).toMatchObject({
      taskId: 't1',
      nodeId: 'n1',
      signed: true,
      assignees: [],
    })
  })

  it('非会签节点不派生会签字段', () => {
    const node = normalizeInstance({ id: 'i', nodes: [{ nodeId: 'n', name: 'n' }] }).nodes[0]
    expect(node.signed).toBe(false)
    expect(signProgress(node)).toBeUndefined()
  })
})

describe('会签聚合与进度', () => {
  it('会签给出 n / m；非会签返回 undefined', () => {
    expect(signProgress(INSTANCE.nodes[1])).toEqual({ done: 1, total: 2 })
    expect(signProgress(INSTANCE.nodes[0])).toBeUndefined()
  })

  it('会签总数缺省取审批人数', () => {
    const node = normalizeInstance({
      id: 'i',
      nodes: [
        {
          nodeId: 'n',
          name: 'n',
          signed: true,
          assignees: [
            { id: 'a', name: 'A' },
            { id: 'b', name: 'B' },
            { id: 'c', name: 'C' },
          ],
        },
      ],
    }).nodes[0]
    expect(signProgress(node)).toEqual({ done: 0, total: 3 })
  })

  it('进度摘要：已完成节点数与当前节点名称', () => {
    expect(resolveProgressSummary(INSTANCE)).toEqual({ done: 1, total: 3, activeName: '主管审批' })
    expect(resolveProgressSummary(normalizeInstance({ id: 'x' }))).toEqual({ done: 0, total: 0, activeName: '' })
  })

  it('当前节点索引：命中 currentNodeId 优先，否则首个 active，皆无 -1', () => {
    expect(resolveActiveNodeIndex(INSTANCE.nodes, 'n3')).toBe(2)
    expect(resolveActiveNodeIndex(INSTANCE.nodes, 'absent')).toBe(1)
    expect(resolveActiveNodeIndex(INSTANCE.nodes, undefined)).toBe(1)
    expect(resolveActiveNodeIndex([], 'n1')).toBe(-1)
  })
})

describe('分支降级与只读判定', () => {
  it('紧凑模式省略未走分支', () => {
    expect(resolveVisibleNodes(INSTANCE.nodes, { compact: true }).map((node) => node.nodeId)).toEqual(['n1', 'n2'])
  })

  it('非紧凑模式把未走分支降级为 skipped', () => {
    const visible = resolveVisibleNodes(INSTANCE.nodes)
    expect(visible).toHaveLength(3)
    expect(visible[2].status).toBe('skipped')
    expect(INSTANCE.nodes[2].status).toBe('pending')
  })

  it('只读判定：finished / rejected / abnormal 为只读', () => {
    expect(resolveReadonlyInstance('running')).toBe(false)
    expect(resolveReadonlyInstance('finished')).toBe(true)
    expect(resolveReadonlyInstance('rejected')).toBe(true)
    expect(resolveReadonlyInstance('abnormal')).toBe(true)
    expect(resolveReadonlyInstance(undefined)).toBe(false)
  })
})

describe('时间线与分组', () => {
  it('正序缺省保持原顺序，倒序按时间逆序', () => {
    expect(resolveTimelineOrderRecords(RECORDS).map((record) => record.id)).toEqual(['r1', 'r2', 'r3'])
    expect(resolveTimelineOrderRecords(RECORDS, 'desc').map((record) => record.id)).toEqual(['r3', 'r2', 'r1'])
  })

  it('同时间倒序保持稳定序', () => {
    const same: ApprovalRecord[] = [
      normalizeRecord({ id: 'a', createdAt: '2026-09-19T09:00:00Z' }),
      normalizeRecord({ id: 'b', createdAt: '2026-09-19T09:00:00Z' }),
    ]
    expect(resolveTimelineOrderRecords(same, 'desc').map((record) => record.id)).toEqual(['b', 'a'])
  })

  it('按节点分组（空节点标识归 ungrouped，节点名取首个非空）', () => {
    const groups = groupRecordsByNode(RECORDS)
    expect(groups.map((group) => group.nodeId)).toEqual(['n1', 'n2', APPROVAL_UNGROUPED])
    expect(groups[0].records).toHaveLength(1)
    expect(groups[2].nodeName).toBe(APPROVAL_UNGROUPED)
  })
})

describe('意见折叠与校验', () => {
  it('折叠按码点截断，未超阈值不折叠', () => {
    expect(foldComment('短意见')).toEqual({ text: '短意见', folded: false })
    const long = '好'.repeat(201)
    const folded = foldComment(long)
    expect(folded.folded).toBe(true)
    expect(countCodePoints(folded.text)).toBe(200)
  })

  it('码点计数：中文与 emoji 均按 1 计', () => {
    expect(countCodePoints('中文')).toBe(2)
    expect(countCodePoints('👍')).toBe(1)
    expect(countCodePoints('👍'.repeat(10))).toBe(10)
  })

  it('必填与超长校验（按码点）', () => {
    expect(validateComment('', { required: true }).valid).toBe(false)
    expect(validateComment('  ', { required: true }).valid).toBe(false)
    expect(validateComment('', { required: false }).valid).toBe(true)
    expect(validateComment('好'.repeat(APPROVAL_COMMENT_MAX)).valid).toBe(true)
    expect(validateComment('好'.repeat(APPROVAL_COMMENT_MAX + 1)).valid).toBe(false)
    expect(validateComment('👍'.repeat(APPROVAL_COMMENT_MAX)).valid).toBe(true)
    expect(validateComment('👍'.repeat(APPROVAL_COMMENT_MAX + 1)).valid).toBe(false)
  })
})

describe('动作校验与可用矩阵', () => {
  it('驳回意见必填、转办目标必填、评论必填、同意可选', () => {
    const context = { canApprove: true, canWithdraw: true, hasTask: true }
    expect(validateAction('reject', { comment: '', ...context }).valid).toBe(false)
    expect(validateAction('reject', { comment: '不通过', ...context }).valid).toBe(true)
    expect(validateAction('transfer', { target: '', ...context }).valid).toBe(false)
    expect(validateAction('transfer', { target: 'u2', ...context }).valid).toBe(true)
    expect(validateAction('comment', { comment: '', ...context }).valid).toBe(false)
    expect(validateAction('approve', { comment: '', ...context }).valid).toBe(true)
  })

  it('动作不可用时校验不通过', () => {
    expect(validateAction('approve', { canApprove: false, hasTask: true }).valid).toBe(false)
    expect(validateAction('approve', { canApprove: true, hasTask: false }).valid).toBe(false)
    expect(validateAction('withdraw', { canWithdraw: false }).valid).toBe(false)
    expect(validateAction('withdraw', { canWithdraw: true, comment: '撤回' }).valid).toBe(true)
  })

  it('可用矩阵：异常实例全不可用；撤回独立于待办', () => {
    expect(resolveApprovalActions({ status: 'running', canApprove: true, hasTask: true })).toEqual({
      approve: true,
      reject: true,
      transfer: true,
      withdraw: false,
      comment: true,
    })
    expect(
      resolveApprovalActions({ status: 'running', canApprove: true, hasTask: true, canWithdraw: true }),
    ).toMatchObject({ withdraw: true })
    expect(resolveApprovalActions({ status: 'abnormal', canApprove: true, hasTask: true })).toEqual({
      approve: false,
      reject: false,
      transfer: false,
      withdraw: false,
      comment: false,
    })
    expect(resolveApprovalActions({ status: 'running', canApprove: true, hasTask: false })).toMatchObject({
      approve: false,
      comment: false,
    })
  })
})

describe('幂等键', () => {
  it('同内容同键、内容变更换键（意见去空白参与派生）', () => {
    const base = deriveApprovalKey('t1', 'approve', '同意', undefined)
    expect(base).toBe(deriveApprovalKey('t1', 'approve', '同意', undefined))
    expect(base).toBe(deriveApprovalKey('t1', 'approve', ' 同意 ', undefined))
    expect(base).not.toBe(deriveApprovalKey('t1', 'approve', '同意！', undefined))
    expect(base).not.toBe(deriveApprovalKey('t1', 'reject', '同意', undefined))
    expect(base).not.toBe(deriveApprovalKey('t2', 'approve', '同意', undefined))
    expect(base).toMatch(/^wf:[0-9a-f]{8}$/)
  })
})

describe('只读图形态与错误码', () => {
  it('三级判定：失败优先、其次 XML、再次图片、皆无 none', () => {
    expect(resolveDiagramMode({ bpmnXml: '<x />' })).toBe('xml')
    expect(resolveDiagramMode({ url: 'https://example.test/a.png' })).toBe('image')
    expect(resolveDiagramMode({})).toBe('none')
    expect(resolveDiagramMode({ bpmnXml: '<x />', failed: true })).toBe('failed')
  })

  it('错误码处置映射：60005 按成功（不置只读）、60009 置只读', () => {
    expect(resolveErrorHandling(60003)).toMatchObject({ handling: 'denied', refresh: true })
    expect(resolveErrorHandling(60005)).toMatchObject({ handling: 'duplicated', refresh: true })
    expect(resolveErrorHandling(60009)).toMatchObject({ handling: 'abnormal', refresh: true, readOnly: true })
    expect(resolveErrorHandling(99999)).toBeUndefined()
    expect(Object.keys(APPROVAL_ERROR_HANDLERS)).toHaveLength(5)
  })

  it('只读图降级文案已定', () => {
    expect(APPROVAL_DIAGRAM_FALLBACK_TEXT).toContain('进度视图')
  })
})
