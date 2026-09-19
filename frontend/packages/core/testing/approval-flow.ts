/**
 * 审批流编排契约（`@bms/core/testing`）。
 *
 * 审批流展示为「同一契约多实现」（PC `ui-ep` / 未来移动端），各自在本套件中传入适配器跑同一套断言。
 * 契约面为**结构化接口**（非具体基类），实现侧可用基类实例或投影适配器接入。
 */

import { describe, expect, it } from 'vitest'

/** 契约目标：节点（最小面）。 */
export interface ApprovalContractNode {
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  name: string
  /** 节点状态。 */
  status?: string
  /** 是否已勾选会签。 */
  signed?: boolean
  /** 会签已完成人数。 */
  signedDone?: number
  /** 会签总人数。 */
  signedTotal?: number
  /** 审批人。 */
  assignees?: { id: string; name: string }[]
}

/** 契约目标：实例（最小面）。 */
export interface ApprovalContractInstance {
  /** 实例标识。 */
  id: string
  /** 实例状态。 */
  status?: string
  /** 当前节点标识。 */
  currentNodeId?: string
  /** 节点序列。 */
  nodes?: readonly ApprovalContractNode[]
  /** BPMN 定义快照。 */
  bpmnXml?: string
}

/** 契约目标：审批记录（最小面）。 */
export interface ApprovalContractRecord {
  /** 记录标识。 */
  id: string
  /** 节点标识。 */
  nodeId?: string
  /** 节点名称。 */
  nodeName?: string
  /** 审批人姓名。 */
  assigneeName?: string
  /** 动作。 */
  action?: string
  /** 意见。 */
  comment?: string
  /** 时间。 */
  createdAt?: string
}

/** 契约目标：提交入参（最小面）。 */
export interface ApprovalContractSubmitInput {
  /** 动作。 */
  action: string
  /** 任务标识。 */
  taskId?: string
  /** 意见。 */
  comment?: string
  /** 目标。 */
  target?: string
  /** 幂等键。 */
  idempotencyKey: string
}

/** 契约处理函数集（结构化最小面；未注入的项按占位）。 */
export interface ApprovalContractHandlers {
  /** 取实例详情。 */
  loadInstance?: (input: { instanceId: string }) => Promise<ApprovalContractInstance | undefined>
  /** 取审批记录。 */
  loadRecords?: (input: { instanceId: string }) => Promise<readonly ApprovalContractRecord[] | undefined>
  /** 取只读图图片地址。 */
  loadDiagramUrl?: () => Promise<{ url: string; expiresAt: number } | undefined>
  /** 提交。 */
  submit?: (input: ApprovalContractSubmitInput) => Promise<{ recordVersion?: number; duplicate?: boolean } | undefined>
}

/** 契约面：审批流编排。 */
export interface ApprovalFlowContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 是否禁用（占位态强制禁用）。 */
  readonly disabled: boolean
  /** 请求计数（占位期恒 0）。 */
  readonly requestCount: number
  /** 当前阶段。 */
  readonly phase: string
  /** 实例状态。 */
  readonly instanceStatus: string | undefined
  /** 节点数。 */
  readonly nodeCount: number
  /** 记录数。 */
  readonly recordCount: number
  /** 是否只读（已结束 / 已驳回 / 异常 / 60009）。 */
  readonly readonlyState: boolean
  /** 只读图形态。 */
  readonly diagramMode: string
  /** 取数次数（含提交后刷新）。 */
  readonly loadCount: number
  /** 进度摘要。 */
  progress(): { done: number; total: number; activeName: string }
  /** 会签进度（非会签返回 `undefined`）。 */
  signProgress(nodeId: string): { done: number; total: number } | undefined
  /** 可用动作矩阵。 */
  actions(): { approve: boolean; reject: boolean; transfer: boolean; withdraw: boolean; comment: boolean }
  /** 失败处置（按错误码解析）。 */
  errorHandling(): { handling: string; refresh: boolean; readOnly?: boolean } | undefined
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入权限码集合（`undefined` 表示不注入权限上下文）。 */
  setAccess(codes: readonly string[] | undefined): void
  /** 注入处理函数集。 */
  setHandlers(handlers: ApprovalContractHandlers): void
  /** 并行取数。 */
  load(): Promise<boolean>
  /** 装载实例。 */
  applyInstance(input: ApprovalContractInstance): void
  /** 装载记录。 */
  applyRecords(input: readonly ApprovalContractRecord[]): void
  /** 装载当前待办。 */
  applyTask(input?: { taskId?: string; nodeId?: string; nodeName?: string }): void
  /** 设置可撤回（宿主下发）。 */
  setWithdrawable(value: boolean): void
  /** 幂等键。 */
  idempotencyKey(action: string, comment?: string, target?: string): string
  /** 动作前置校验。 */
  validate(action: string, input?: { comment?: string; target?: string }): { valid: boolean; message: string }
  /** 提交。 */
  submit(action: string, input?: { comment?: string; target?: string }): Promise<unknown>
  /** 重试失败提交。 */
  retry(): Promise<unknown>
  /** 只读图图片通路取址。 */
  loadDiagramImage(): Promise<string | undefined>
  /** 标记只读图失败。 */
  markDiagramFailed(): void
}

/** 契约目标约定：实例（进行中，含会签节点与未走节点）。 */
const INSTANCE: ApprovalContractInstance = {
  id: 'wf-1',
  status: 'running',
  currentNodeId: 'n2',
  bpmnXml: '<definitions><process><startEvent id="s1" /></process></definitions>',
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

/** 契约目标约定：审批记录。 */
const RECORDS: readonly ApprovalContractRecord[] = [
  { id: 'r1', nodeId: 'n1', nodeName: '发起', assigneeName: '王五', action: 'approve', comment: '同意', createdAt: '2026-09-19T09:00:00Z' },
  { id: 'r2', nodeId: 'n2', nodeName: '主管审批', assigneeName: '张三', action: 'comment', comment: '请补充附件', createdAt: '2026-09-19T10:00:00Z' },
]

/**
 * 审批流编排契约（`BaseApprovalFlow` / `useBaseApprovalFlow` 投影；`08-8-1` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：实例 `wf-1`（`running`，节点 `n1 done` / `n2 active signed`（2 人、已完成 1）/ `n3 pending`，
 * `currentNodeId = n2`）；记录两条；当前待办 `task-1`；权限上下文含 `wf:approve`；初始未注入处理函数。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeApprovalFlowContract(name: string, create: () => ApprovalFlowContractTarget): void {
  /**
   * 构造「已就绪且已装载」的目标。
   *
   * 缺省注入只读图图片通路取址（`loadDiagramUrl`），使「XML → 图片 → 失败」三级判定可完整断言；
   * `withDiagram` 为假时不注入该取址（用于断言「未注入即占位、零请求」）。
   *
   * @param handlers 处理函数集（覆盖缺省项）。
   * @param options 选项（`withDiagram` 缺省为真）。
   * @returns 契约目标。
   */
  const readyTarget = (
    handlers: ApprovalContractHandlers = {},
    options: { withDiagram?: boolean } = {},
  ): ApprovalFlowContractTarget => {
    const target = create()
    const merged: ApprovalContractHandlers =
      options.withDiagram === false
        ? { ...handlers }
        : {
            loadDiagramUrl: async () => ({ url: 'https://example.test/diagram.png', expiresAt: Date.now() + 60_000 }),
            ...handlers,
          }
    target.setHandlers(merged)
    target.setReady(true)
    target.applyInstance(INSTANCE)
    target.applyRecords(RECORDS)
    target.applyTask({ taskId: 'task-1', nodeId: 'n2', nodeName: '主管审批' })
    return target
  }

  describe(name, () => {
    it('未就绪时降级且禁用，不产生请求', async () => {
      const target = create()
      target.setHandlers({ loadInstance: async () => INSTANCE })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.disabled).toBe(true)
      await target.load()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入处理函数时不产生请求、不再降级', async () => {
      const target = create()
      target.setReady(true)
      expect(target.degraded).toBe(false)
      expect(target.disabled).toBe(false)
      await target.load()
      expect(target.requestCount).toBe(0)
    })

    it('并行取数：两侧各自结算，请求计数按实际发起数累加', async () => {
      const target = create()
      target.setHandlers({
        loadInstance: async () => INSTANCE,
        loadRecords: async () => RECORDS,
      })
      target.setReady(true)
      await expect(target.load()).resolves.toBe(true)
      expect(target.requestCount).toBe(2)
      expect(target.instanceStatus).toBe('running')
      expect(target.nodeCount).toBe(3)
      expect(target.recordCount).toBe(2)
    })

    it('取数单失败不整体报错：成功面仍可读', async () => {
      const target = create()
      target.setHandlers({
        loadInstance: async () => INSTANCE,
        loadRecords: async () => {
          throw new Error('记录接口异常')
        },
      })
      target.setReady(true)
      await expect(target.load()).resolves.toBe(false)
      expect(target.nodeCount).toBe(3)
      expect(target.recordCount).toBe(0)
    })

    it('会签聚合：signed 为假无聚合，真则给出 n / m', () => {
      const target = readyTarget()
      expect(target.signProgress('n2')).toEqual({ done: 1, total: 2 })
      expect(target.signProgress('n1')).toBeUndefined()
    })

    it('进度摘要与当前节点名称', () => {
      const target = readyTarget()
      expect(target.progress()).toEqual({ done: 1, total: 3, activeName: '主管审批' })
    })

    it('动作可用矩阵：进行中且有权限时审批动作可用；撤回独立', () => {
      const target = readyTarget()
      target.setAccess(['wf:approve'])
      target.setWithdrawable(true)
      expect(target.actions()).toEqual({
        approve: true,
        reject: true,
        transfer: true,
        withdraw: true,
        comment: true,
      })
    })

    it('无当前待办时审批动作不可用；实例结束则全不可用', () => {
      const target = readyTarget()
      target.setAccess(['wf:approve'])
      target.setWithdrawable(true)
      target.applyTask(undefined)
      expect(target.actions().approve).toBe(false)
      expect(target.actions().withdraw).toBe(true)

      target.applyTask({ taskId: 'task-1', nodeId: 'n2' })
      target.applyInstance({ ...INSTANCE, status: 'finished' })
      expect(target.readonlyState).toBe(true)
      expect(target.actions().approve).toBe(false)
      expect(target.actions().withdraw).toBe(false)
    })

    it('无权（缺 wf:approve）时不可审批', () => {
      const target = readyTarget()
      target.setAccess([])
      expect(target.actions().approve).toBe(false)
      target.setAccess(['wf:approve'])
      expect(target.actions().approve).toBe(true)
    })

    it('动作前置校验：驳回意见必填、转办目标必填、超长意见拒绝', () => {
      const target = readyTarget()
      target.setAccess(['wf:approve'])

      expect(target.validate('reject', { comment: '' }).valid).toBe(false)
      expect(target.validate('reject', { comment: '不通过' }).valid).toBe(true)
      expect(target.validate('transfer', { target: '' }).valid).toBe(false)
      expect(target.validate('transfer', { target: 'u2' }).valid).toBe(true)

      const long = '好'.repeat(4001)
      expect(target.validate('approve', { comment: long }).valid).toBe(false)
      expect(target.validate('approve', { comment: '好'.repeat(4000) }).valid).toBe(true)
    })

    it('幂等键：同内容同键、内容变更换键', () => {
      const target = readyTarget()
      const first = target.idempotencyKey('approve', '同意', undefined)
      expect(first).toBe(target.idempotencyKey('approve', '同意', undefined))
      expect(first).not.toBe(target.idempotencyKey('approve', '同意！', undefined))
      expect(first).not.toBe(target.idempotencyKey('reject', '同意', undefined))
      expect(first).toMatch(/^wf:[0-9a-f]{8}$/)
    })

    it('提交成功：载荷携带幂等键、提交后刷新取数', async () => {
      const seen: string[] = []
      const target = readyTarget({
        loadInstance: async () => INSTANCE,
        loadRecords: async () => RECORDS,
        submit: async (input) => {
          seen.push(input.idempotencyKey)
          return { recordVersion: 3 }
        },
      })
      target.setAccess(['wf:approve'])
      const before = target.loadCount
      await target.submit('approve', { comment: '同意' })
      expect(seen).toHaveLength(1)
      expect(seen[0]).toBe(target.idempotencyKey('approve', '同意', undefined))
      expect(target.phase).toBe('done')
      expect(target.loadCount).toBeGreaterThan(before)
    })

    it('重复提交按成功处理（60005）', async () => {
      const target = readyTarget({
        submit: async () => {
          throw Object.assign(new Error('重复提交被拦截'), { code: 60005 })
        },
      })
      target.setAccess(['wf:approve'])
      await target.submit('approve', { comment: '同意' })
      expect(target.phase).toBe('done')
      expect(target.errorHandling()?.handling).toBe('duplicated')
      expect(target.readonlyState).toBe(false)
    })

    it('越权（60003）/ 状态不允许（60004）/ 会签未完成（60008）按错误码处置并刷新', async () => {
      for (const code of [60003, 60004, 60008]) {
        const target = readyTarget({
          loadInstance: async () => INSTANCE,
          loadRecords: async () => RECORDS,
          submit: async () => {
            throw Object.assign(new Error('业务拒绝'), { code })
          },
        })
        target.setAccess(['wf:approve'])
        const before = target.loadCount
        await target.submit('approve', { comment: '同意' })
        expect(target.phase).toBe('failed')
        expect(target.errorHandling()?.handling).not.toBe('duplicated')
        expect(target.loadCount).toBeGreaterThan(before)
      }
    })

    it('引擎异常（60009）置只读', async () => {
      const target = readyTarget({
        submit: async () => {
          throw Object.assign(new Error('引擎异常'), { code: 60009 })
        },
      })
      target.setAccess(['wf:approve'])
      await target.submit('approve', { comment: '同意' })
      expect(target.readonlyState).toBe(true)
      expect(target.errorHandling()?.readOnly).toBe(true)
      expect(target.actions().approve).toBe(false)
    })

    it('未注入提交处理时不请求且保留本地状态', async () => {
      const target = readyTarget({ loadInstance: async () => INSTANCE })
      target.setAccess(['wf:approve'])
      const before = target.requestCount
      await expect(target.submit('approve', { comment: '同意' })).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)
      expect(target.phase).toBe('idle')
    })

    it('校验不通过时不请求（意见必填）', async () => {
      const target = readyTarget({ submit: async () => ({ recordVersion: 1 }) })
      target.setAccess(['wf:approve'])
      const before = target.requestCount
      await expect(target.submit('reject', { comment: '' })).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)
    })

    it('进行中重复提交不动作', async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      let calls = 0
      const target = readyTarget({
        submit: async () => {
          calls += 1
          await gate
          return { recordVersion: 1 }
        },
      })
      target.setAccess(['wf:approve'])
      const pending = target.submit('approve', { comment: '同意' })
      await expect(target.submit('approve', { comment: '同意' })).resolves.toBeUndefined()
      release()
      await pending
      expect(calls).toBe(1)
    })

    it('只读图形态三级判定与失败标记', async () => {
      const target = readyTarget()
      expect(target.diagramMode).toBe('xml')

      target.applyInstance({ ...INSTANCE, bpmnXml: '' })
      expect(target.diagramMode).toBe('none')

      await target.loadDiagramImage()
      expect(target.diagramMode).toBe('image')

      target.markDiagramFailed()
      expect(target.diagramMode).toBe('failed')
    })

    it('只读图未注入取址时不产生请求', async () => {
      const target = readyTarget({}, { withDiagram: false })
      const before = target.requestCount
      await expect(target.loadDiagramImage()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)
    })
  })
}
