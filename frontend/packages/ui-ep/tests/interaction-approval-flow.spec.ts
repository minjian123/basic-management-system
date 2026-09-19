// kiwi_id: 775
/** 审批流展示用例（08_8_1）：契约套件驱动 + 投影薄适配 + 四件组件（进度 / 时间线 / 操作面板 / 只读图）与容器装配。 */

import {
  BaseAccess,
  countCodePoints,
  foldComment,
  APPROVAL_COMMENT_MAX,
  type ApprovalInstanceInput,
  type ApprovalJobs,
} from '@bms/core'
import {
  describeApprovalFlowContract,
  type ApprovalContractHandlers,
  type ApprovalContractInstance,
  type ApprovalContractRecord,
  type ApprovalFlowContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import {
  ApprovalActionPanel,
  ApprovalFlow,
  ApprovalProgress,
  ApprovalTimeline,
  useBaseApprovalFlow,
} from '../src'

// bpmn-js 依赖 SVG 的 `getBBox`（jsdom 不实现）：对画布创建入口下桩，真实渲染在核对页以 chromium 核验。
vi.mock('../src/utils/bpmnCanvas', () => ({
  createBpmnCanvas: vi.fn(async () => ({
    mode: 'viewer',
    instance: {},
    importXml: async () => undefined,
    saveXml: async () => '<bpmn:definitions />',
    on: () => () => undefined,
    select: () => undefined,
    highlight: () => undefined,
    scrollTo: () => undefined,
    zoomBy: () => undefined,
    zoomTo: () => undefined,
    fitViewport: () => undefined,
    undo: () => undefined,
    redo: () => undefined,
    canUndo: () => false,
    canRedo: () => false,
    createElement: () => undefined,
    updateProperties: () => undefined,
    destroy: () => undefined,
  })),
}))

/** 样例实例（进行中，含会签与未走节点）。 */
const INSTANCE: ApprovalInstanceInput = {
  id: 'wf-1',
  status: 'running',
  currentNodeId: 'n2',
  bpmnXml: '<bpmn:definitions />',
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
}

/** 样例记录（含长意见与附件）。 */
const RECORDS = [
  {
    id: 'r1',
    nodeId: 'n1',
    nodeName: '发起',
    assigneeId: 'u9',
    assigneeName: '王五',
    action: 'approve' as const,
    comment: '同意',
    createdAt: '2026-09-19T09:00:00Z',
    attachments: [],
  },
  {
    id: 'r2',
    nodeId: 'n2',
    nodeName: '主管审批',
    assigneeId: 'u1',
    assigneeName: '张三',
    action: 'comment' as const,
    comment: '好'.repeat(260),
    createdAt: '2026-09-19T10:00:00Z',
    attachments: [{ id: 'a1', name: '补充说明.pdf' }],
  },
]

/** 权限上下文（可实例化）。 */
class SampleAccess extends BaseAccess {}

/**
 * 在独立作用域内执行（组合式投影需要活动作用域）。
 *
 * @param factory 工厂函数。
 */
function scoped<T>(factory: () => T): T {
  const scope = effectScope()
  const result = scope.run(factory)
  if (result === undefined) {
    throw new Error('effectScope 未返回结果')
  }
  return result
}

/** 审批流编排契约目标（`useBaseApprovalFlow` 投影）。 */
function approvalTarget(): ApprovalFlowContractTarget {
  return scoped(() => {
    const api = useBaseApprovalFlow()
    const access = new SampleAccess()
    let loadCount = 0
    return {
      get ready() {
        return api.ready.value
      },
      get degraded() {
        return api.degraded.value
      },
      get disabled() {
        return api.disabled.value
      },
      get requestCount() {
        return api.requestCount.value
      },
      get phase() {
        return api.phase.value
      },
      get instanceStatus() {
        return api.instance.value?.status
      },
      get nodeCount() {
        return api.instance.value?.nodes.length ?? 0
      },
      get recordCount() {
        return api.records.value.length
      },
      get readonlyState() {
        return api.readonly.value
      },
      get diagramMode() {
        return api.diagramMode.value
      },
      get loadCount() {
        return loadCount
      },
      progress: () => api.progress.value,
      signProgress: (nodeId: string) =>
        api.instance.value?.nodes.find((node) => node.nodeId === nodeId)?.signed === true
          ? {
              done: api.instance.value.nodes.find((node) => node.nodeId === nodeId)?.signedDone ?? 0,
              total: api.instance.value.nodes.find((node) => node.nodeId === nodeId)?.signedTotal ?? 0,
            }
          : undefined,
      actions: () => api.actions.value,
      errorHandling: () => api.errorHandling.value,
      setReady: (value: boolean) => api.setReady(value),
      setAccess: (codes) => {
        access.setCodes(codes ?? [])
        api.setAccess(codes === undefined ? undefined : access)
      },
      setHandlers: (handlers: ApprovalContractHandlers) => {
        const jobs: ApprovalJobs = {}
        if (handlers.loadInstance !== undefined) {
          jobs.loadInstance = async ({ instanceId }) => {
            const result = await handlers.loadInstance?.({ instanceId })
            loadCount += 1
            return result === undefined ? undefined : (result as ApprovalInstanceInput)
          }
        }
        if (handlers.loadRecords !== undefined) {
          jobs.loadRecords = async ({ instanceId }) => {
            const result = await handlers.loadRecords?.({ instanceId })
            loadCount += 1
            return result === undefined ? undefined : (result as never)
          }
        }
        if (handlers.loadDiagramUrl !== undefined) {
          jobs.loadDiagramUrl = async () => handlers.loadDiagramUrl?.()
        }
        if (handlers.submit !== undefined) {
          jobs.submit = async (payload) =>
            handlers.submit?.({
              action: payload.action,
              taskId: payload.taskId,
              comment: payload.comment,
              target: payload.target,
              idempotencyKey: payload.idempotencyKey,
            })
        }
        api.setJobs(jobs)
      },
      load: () => api.load(),
      applyInstance: (input: ApprovalContractInstance) => api.applyInstance(input as ApprovalInstanceInput),
      applyRecords: (input: readonly ApprovalContractRecord[]) => api.applyRecords(input as never),
      applyTask: (input) => api.applyTask(input as never),
      setWithdrawable: (value: boolean) => api.setWithdrawable(value),
      idempotencyKey: (action, comment, target) => api.idempotencyKey(action as never, comment, target),
      validate: (action, input) => api.validate(action as never, input),
      submit: (action, input) => api.submit(action as never, input),
      retry: () => api.retry(),
      loadDiagramImage: () => api.loadDiagramImage(),
      markDiagramFailed: () => api.markDiagramFailed(),
    }
  })
}

describeApprovalFlowContract('审批流编排契约（useBaseApprovalFlow 投影）', approvalTarget)

describe('投影薄适配', () => {
  it('就绪态装载实例与记录并派生进度、动作与幂等键', () => {
    const api = scoped(() => {
      const result = useBaseApprovalFlow({ ready: true })
      result.applyInstance(INSTANCE)
      result.applyRecords(RECORDS as never)
      result.applyTask({ taskId: 'task-1', nodeId: 'n2', nodeName: '主管审批' })
      result.setWithdrawable(true)
      const access = new SampleAccess()
      access.setCodes(['wf:approve'])
      result.setAccess(access)
      return result
    })
    expect(api.progress.value).toEqual({ done: 1, total: 3, activeName: '主管审批' })
    expect(api.actions.value.approve).toBe(true)
    expect(api.actions.value.withdraw).toBe(true)
    expect(api.idempotencyKey('approve', '同意')).toMatch(/^wf:[0-9a-f]{8}$/)
    expect(api.records.value).toHaveLength(2)
  })

  it('注入处理函数后并行取数并按实际发起数计数', async () => {
    const api = scoped(() => useBaseApprovalFlow({ ready: true }))
    api.setJobs({
      loadInstance: async () => INSTANCE,
      loadRecords: async () => RECORDS as never,
    })
    await expect(api.load()).resolves.toBe(true)
    expect(api.requestCount.value).toBe(2)
    expect(api.instanceState.value).toBe('ready')
    expect(api.recordsState.value).toBe('ready')
  })
})

describe('ApprovalProgress 流程进度件', () => {
  it('三形态与状态语义、会签聚合与展开', async () => {
    const horizontal = mount(ApprovalProgress, {
      props: { nodes: INSTANCE.nodes, currentNodeId: 'n2', instanceStatus: 'running' },
    })
    expect(horizontal.attributes('data-direction')).toBe('horizontal')
    expect(horizontal.find('[data-test="node-n2"]').attributes('data-status')).toBe('active')
    expect(horizontal.find('[data-test="sign-progress"]').text()).toBe('已完成 1 / 共 2')

    await horizontal.find('[data-test="signed"]').trigger('click')
    const panel = horizontal.find('[data-test="signed-panel"]')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('张三（已处理）')
    expect(panel.text()).toContain('李四（待处理）')

    const vertical = mount(ApprovalProgress, {
      props: { nodes: INSTANCE.nodes, direction: 'vertical', currentNodeId: 'n2' },
    })
    expect(vertical.attributes('data-direction')).toBe('vertical')
  })

  it('紧凑模式省略未走分支，非紧凑把未走分支降级为跳过', () => {
    const compact = mount(ApprovalProgress, { props: { nodes: INSTANCE.nodes, compact: true } })
    expect(compact.find('[data-test="node-n3"]').exists()).toBe(false)

    const full = mount(ApprovalProgress, { props: { nodes: INSTANCE.nodes } })
    expect(full.find('[data-test="node-n3"]').attributes('data-status')).toBe('skipped')
  })

  it('节点点击上抛并给出进度摘要', async () => {
    const wrapper = mount(ApprovalProgress, { props: { nodes: INSTANCE.nodes, currentNodeId: 'n2' } })
    await wrapper.find('[data-test="node-n1"]').trigger('click')
    expect(wrapper.emitted('node-click')?.[0]).toEqual(['n1'])
    expect(wrapper.find('[data-test="progress-summary"]').text()).toContain('已完成 1 / 3 节点')
  })

  it('空节点出空态', () => {
    const wrapper = mount(ApprovalProgress, { props: { nodes: [] } })
    expect(wrapper.find('[data-test="progress-empty"]').exists()).toBe(true)
  })
})

describe('ApprovalTimeline 审批时间线件', () => {
  it('正序缺省、切换倒序、分组与高亮动作', async () => {
    const wrapper = mount(ApprovalTimeline, {
      props: { records: RECORDS, grouped: true, highlightAction: 'approve' },
    })
    expect(wrapper.attributes('data-order')).toBe('asc')
    expect(wrapper.find('[data-test="record-r1"]').attributes('data-highlight')).toBe('true')
    expect(wrapper.find('[data-test="record-group-n2"]').exists()).toBe(true)

    await wrapper.find('[data-test="timeline-order"]').trigger('click')
    expect(wrapper.attributes('data-order')).toBe('desc')
    expect(wrapper.emitted('order-change')?.[0]).toEqual(['desc'])
  })

  it('长意见折叠与展开、附件点击上抛', async () => {
    const wrapper = mount(ApprovalTimeline, { props: { records: RECORDS } })
    const comment = wrapper.find('[data-test="record-r2"]').text()
    expect(countCodePoints(comment.replace('展开', ''))).toBeLessThan(APPROVAL_COMMENT_MAX)
    expect(foldComment('好'.repeat(260)).folded).toBe(true)

    await wrapper.find('[data-test="fold-r2"]').trigger('click')
    expect(wrapper.emitted('fold-toggle')?.[0]).toEqual([{ recordId: 'r2', folded: true }])

    await wrapper.find('[data-test="attachment-a1"]').trigger('click')
    expect(wrapper.emitted('attachment-click')?.[0]?.[0]).toMatchObject({ recordId: 'r2' })
  })

  it('无记录出空态', () => {
    const wrapper = mount(ApprovalTimeline, { props: { records: [] } })
    expect(wrapper.find('[data-test="empty-records"]').exists()).toBe(true)
  })
})

describe('ApprovalActionPanel 审批操作面板件', () => {
  const actions = { approve: true, reject: true, transfer: true, withdraw: false, comment: true }

  it('按可用矩阵渲染按钮并透传意见与任务', async () => {
    const wrapper = mount(ApprovalActionPanel, {
      props: { actions, currentTask: { taskId: 't1', nodeId: 'n2' } },
    })
    expect(wrapper.find('[data-test="withdraw"]').exists()).toBe(false)

    await wrapper.find('[data-test="comment-input"]').setValue('同意')
    await wrapper.find('[data-test="approve"]').trigger('click')
    expect(wrapper.emitted('action')?.[0]).toEqual([
      { action: 'approve', taskId: 't1', comment: '同意', target: undefined },
    ])
  })

  it('驳回意见必填拦截、填后放行并携带退回节点', async () => {
    const wrapper = mount(ApprovalActionPanel, {
      props: {
        actions,
        currentTask: { taskId: 't1', nodeId: 'n2' },
        returnableNodes: [{ nodeId: 'n1', name: '发起' }],
      },
    })
    await wrapper.find('[data-test="reject"]').trigger('click')
    expect(wrapper.find('[data-test="comment-error"]').text()).toContain('意见')
    expect(wrapper.emitted('action')).toBeUndefined()

    await wrapper.find('[data-test="comment-input"]').setValue('不通过')
    await wrapper.find('[data-test="reject"]').trigger('click')
    await wrapper.find('[data-test="reject-target"]').setValue('n1')
    await wrapper.find('[data-test="reject"]').trigger('click')
    expect(wrapper.emitted('action')?.at(-1)?.[0]).toMatchObject({ action: 'reject', comment: '不通过', target: 'n1' })
  })

  it('转办目标必填、意见按码点计数', async () => {
    const wrapper = mount(ApprovalActionPanel, {
      props: { actions, currentTask: { taskId: 't1', nodeId: 'n2' }, transferCandidates: [{ id: 'u2', name: '李四' }] },
    })
    await wrapper.find('[data-test="transfer"]').trigger('click')
    expect(wrapper.find('[data-test="transfer-target"]').exists()).toBe(true)
    await wrapper.find('[data-test="transfer-target"]').setValue('u2')
    await wrapper.find('[data-test="transfer"]').trigger('click')
    expect(wrapper.emitted('action')?.at(-1)?.[0]).toMatchObject({ action: 'transfer', target: 'u2' })
  })

  it('只读态不出按钮并提示', () => {
    const wrapper = mount(ApprovalActionPanel, { props: { actions, readonly: true } })
    expect(wrapper.find('[data-test="approve"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="readonly-tip"]').exists()).toBe(true)
  })
})

describe('ApprovalFlow 容器装配', () => {
  const baseProps = {
    ready: true,
    instance: INSTANCE,
    records: RECORDS,
    currentTask: { taskId: 't1', nodeId: 'n2', nodeName: '主管审批' },
    canApprove: true,
    canWithdraw: true,
    showDiagram: true,
    autoLoad: false,
  }

  it('装配进度、时间线与操作面板并透传动作', async () => {
    const wrapper = mount(ApprovalFlow, { props: baseProps })
    expect(wrapper.find('[data-test="approval-progress"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="approval-timeline"]').exists()).toBe(true)

    await wrapper.find('[data-test="approve"]').trigger('click')
    expect(wrapper.emitted('action')?.[0]?.[0]).toMatchObject({ action: 'approve', taskId: 't1' })
  })

  it('驳回注入提交时打开弹窗（未确认前零提交）', async () => {
    const submitted: string[] = []
    const wrapper = mount(ApprovalFlow, {
      props: {
        ...baseProps,
        jobs: {
          submit: async (payload) => {
            submitted.push(payload.action)
            return { recordVersion: 1 }
          },
        },
      },
      global: {
        // EP 壳件在 jsdom 下不渲染默认插槽，用桩承载弹窗内容以便断言。
        stubs: {
          ElDialog: {
            props: ['modelValue', 'title'],
            template: '<div data-test="shell-dialog"><slot /><slot name="footer" /></div>',
          },
        },
      },
    })
    await wrapper.find('[data-test="reject"]').trigger('click')
    await flushPromises()
    // 弹窗打开后仍未提交（待二次确认）。
    expect(wrapper.find('[data-test="reject-comment"]').exists()).toBe(true)
    expect(submitted).toEqual([])
  })

  it('撤回经危险确认后提交（取消则不提交）', async () => {
    const submitted: string[] = []
    const wrapper = mount(ApprovalFlow, {
      props: {
        ...baseProps,
        jobs: {
          submit: async (payload) => {
            submitted.push(payload.action)
            return { recordVersion: 1 }
          },
        },
      },
    })
    await wrapper.find('[data-test="withdraw"]').trigger('click')
    await flushPromises()
    // 未确认时零提交（确认弹窗由宿主挂载的 ConfirmDialog 结算）。
    expect(submitted).toEqual([])
  })

  it('只读图按需异步分包加载并透传当前节点', async () => {
    const wrapper = mount(ApprovalFlow, { props: baseProps })
    await vi.dynamicImportSettled()
    await flushPromises()
    const diagram = wrapper.find('[data-test="bpmn-diagram"]')
    expect(diagram.exists()).toBe(true)
    expect(diagram.attributes('data-subpackage')).toBe('bpmn')
    expect(diagram.attributes('data-node')).toBe('n2')
  })

  it('无 XML 时只读图降级为进度视图提示', async () => {
    const wrapper = mount(ApprovalFlow, {
      props: { ...baseProps, instance: { ...INSTANCE, bpmnXml: '' } },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="diagram-degrade"]').exists()).toBe(true)
  })
})
