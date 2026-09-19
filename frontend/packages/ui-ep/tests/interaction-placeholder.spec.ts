// kiwi_id: 760
/** 占位版交互件用例（08_01_01）：共享占位契约套件 + 三件（权限配置 / 审批流展示 / 流程建模器）降级与就绪行为 + 分包懒加载。 */

import { describePlaceholderInteractionContract, type PlaceholderInteractionContractTarget } from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { ApprovalFlow, PermissionConfig, ProcessModeler, useInteractionPlaceholder } from '../src'
import ProcessCanvas from '../src/components/approval/ProcessCanvas.vue'

// bpmn-js 依赖 SVG 的 `getBBox`（jsdom 不实现），故对画布创建入口下桩：真实渲染在开发态核对页以 chromium 核验，
// 用例只断言分包边界与载荷透传。
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

/** 合法最小流程 XML（建模器就绪态用例基准）。 */
const VALID_BPMN_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="start1" name="发起" />',
  '    <bpmn:userTask id="tsk1" name="主管审批" />',
  '    <bpmn:endEvent id="end1" name="结束" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="tsk1" />',
  '    <bpmn:sequenceFlow id="f2" sourceRef="tsk1" targetRef="end1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/** 契约目标：占位组合式投影。 */
function makeTarget(): PlaceholderInteractionContractTarget {
  const placeholder = useInteractionPlaceholder()
  return {
    get ready() {
      return placeholder.ready.value
    },
    get degraded() {
      return placeholder.degraded.value
    },
    get disabled() {
      return placeholder.disabled.value
    },
    get requestCount() {
      return placeholder.requestCount.value
    },
    setReady: (value) => placeholder.setReady(value),
    load: () => placeholder.markLoaded(),
  }
}

describePlaceholderInteractionContract('占位交互契约（useInteractionPlaceholder）', makeTarget)

describe('交互占位组合式', () => {
  it('就绪后才允许计入加载，状态经数据状态基类投影', () => {
    const placeholder = useInteractionPlaceholder()
    placeholder.markLoaded()
    expect(placeholder.requestCount.value).toBe(0)
    expect(placeholder.state.value).toBe('empty')

    placeholder.setReady(true)
    expect(placeholder.ready.value).toBe(true)
    expect(placeholder.degraded.value).toBe(false)
    expect(placeholder.disabled.value).toBe(false)
    expect(placeholder.state.value).toBe('ready')

    placeholder.markLoaded()
    expect(placeholder.requestCount.value).toBe(1)
  })
})

describe('PermissionConfig 权限配置', () => {
  const treeNodes = [
    {
      key: 'menu1',
      label: '用户管理',
      type: 'menu' as const,
      children: [
        { key: 'business1', label: '用户列表', type: 'business' as const },
        { key: 'action1', label: '新增用户', type: 'action' as const },
      ],
    },
  ]

  it('占位态降级且不渲染页签', () => {
    const wrapper = mount(PermissionConfig, { props: {} })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('权限配置未就绪')
    expect(wrapper.find('[data-test="tabs"]').exists()).toBe(false)
  })

  it('就绪态渲染权限树、推导只读与提交事件', async () => {
    const wrapper = mount(PermissionConfig, { props: { ready: true, treeNodes, dirty: true } })
    expect(wrapper.attributes('data-degraded')).toBe('false')
    expect(wrapper.find('[data-test="node-menu1"]').text()).toContain('用户管理')
    expect(wrapper.find('[data-test="node-business1"] [data-test="derived"]').text()).toBe('推导')
    expect(wrapper.find('[data-test="dirty"]').text()).toBe('未保存')

    await wrapper.find('[data-test="tab-field"]').trigger('click')
    expect(wrapper.emitted('update:tab')?.[0]).toEqual(['field'])

    await wrapper.find('[data-test="node-check-menu1"]').trigger('change')
    expect(wrapper.emitted('change')?.[0]).toEqual([
      { kind: 'tree', value: { key: 'menu1', checked: true } },
    ])

    await wrapper.find('[data-test="save"]').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
    await wrapper.find('[data-test="reset"]').trigger('click')
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })

  it('字段矩阵 / 数据范围 / 主体绑定页签渲染与编辑事件', async () => {
    const fieldPerms = [
      {
        formKey: 'f1',
        formLabel: '用户表单',
        fields: [{ key: 'name', label: '姓名', visible: true, editable: true }],
      },
    ]
    const field = mount(PermissionConfig, { props: { ready: true, tab: 'field', fieldPerms } })
    expect(field.find('[data-test="form-f1"]').text()).toContain('用户表单')
    await field.find('[data-test="field-f1-name"] input').trigger('change')
    expect(field.emitted('change')?.[0]).toEqual([
      { kind: 'field', value: { formKey: 'f1', fieldKey: 'name', key: 'visible', value: false } },
    ])

    const scope = mount(PermissionConfig, {
      props: {
        ready: true,
        tab: 'scope',
        dataScopes: [{ actionKey: 'act1', actionLabel: '查询', expression: 'dept_id = @current_dept' }],
      },
    })
    expect(scope.find('[data-test="scope-act1"]').text()).toContain('dept_id = @current_dept')

    const subject = mount(PermissionConfig, {
      props: { ready: true, tab: 'subject', subjects: [{ id: 'u1', type: 'user', name: '张三' }] },
    })
    expect(subject.find('[data-test="subject-u1"]').text()).toBe('张三')
  })
})

describe('ApprovalFlow 审批流展示', () => {
  const instance = {
    id: 'i1',
    status: 'running' as const,
    currentNodeId: 'n2',
    bpmnXml: '<bpmn:definitions />',
    nodes: [
      { nodeId: 'n1', name: '发起', status: 'done' as const },
      { nodeId: 'n2', name: '主管审批', status: 'active' as const, signed: true, signedDone: 1, signedTotal: 2 },
    ],
  }
  const records = [
    {
      id: 'r1',
      nodeId: 'n1',
      nodeName: '发起',
      assigneeId: 'u1',
      assigneeName: '张三',
      action: 'approve' as const,
      comment: '同意',
      createdAt: '2026-09-18',
      attachments: [],
    },
  ]

  it('占位态降级，操作不提交', () => {
    const wrapper = mount(ApprovalFlow, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('审批数据未就绪')
    expect(wrapper.find('[data-test="actions"]').exists()).toBe(false)
  })

  it('就绪态渲染进度与时间线，操作按权限透传', async () => {
    const wrapper = mount(ApprovalFlow, {
      props: {
        ready: true,
        instance,
        records,
        currentTask: { taskId: 't1', nodeId: 'n2', nodeName: '主管审批', signed: false, assignees: [] },
        canApprove: true,
        canWithdraw: true,
      },
    })
    expect(wrapper.find('[data-test="approval-progress"] [data-status="active"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="approval-progress"] [data-test="signed"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="record-r1"]').text()).toContain('同意')

    await wrapper.findAll('[data-test="approval-progress"] li')[0].trigger('click')
    expect(wrapper.emitted('node-click')?.[0]).toEqual(['n1'])

    await wrapper.find('[data-test="approve"]').trigger('click')
    expect(wrapper.emitted('action')?.[0]).toEqual([
      { action: 'approve', taskId: 't1', comment: undefined, target: undefined },
    ])
    // 驳回意见必填：未填意见时面板拦截不上抛（校验行为）。
    await wrapper.find('[data-test="reject"]').trigger('click')
    expect(wrapper.emitted('action')).toHaveLength(1)
    expect(wrapper.find('[data-test="comment-error"]').text()).toContain('意见')

    await wrapper.find('[data-test="comment-input"]').setValue('不同意')
    await wrapper.find('[data-test="reject"]').trigger('click')
    expect(wrapper.emitted('action')?.[1]).toEqual([
      { action: 'reject', taskId: 't1', comment: '不同意', target: undefined },
    ])
  })

  it('无审批权限时按钮不渲染', () => {
    const wrapper = mount(ApprovalFlow, { props: { ready: true, instance } })
    expect(wrapper.find('[data-test="approve"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="withdraw"]').exists()).toBe(false)
  })

  it('只读图按需异步加载，无 XML 时降级为进度视图', async () => {
    const diagram = mount(ApprovalFlow, {
      props: { ready: true, instance, showDiagram: true, bpmnXml: '<bpmn:definitions />', autoLoad: false },
    })
    expect(diagram.find('[data-test="bpmn-diagram"]').exists()).toBe(false)
    await vi.dynamicImportSettled()
    await flushPromises()
    const loaded = diagram.find('[data-test="bpmn-diagram"]')
    expect(loaded.exists()).toBe(true)
    expect(loaded.attributes('data-subpackage')).toBe('bpmn')
    expect(loaded.attributes('data-node')).toBe('n2')

    const fallback = mount(ApprovalFlow, {
      props: { ready: true, instance: { ...instance, bpmnXml: '' }, showDiagram: true, autoLoad: false },
    })
    expect(fallback.find('[data-test="diagram-degrade"]').exists()).toBe(true)
  })
})

describe('ProcessModeler 流程建模器', () => {
  it('占位态降级且不渲染工具栏', () => {
    const wrapper = mount(ProcessModeler, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('流程建模器未就绪')
    expect(wrapper.find('[data-test="toolbar"]').exists()).toBe(false)
  })

  it('就绪态渲染三区、调板与提交事件，画布异步分包', async () => {
    const wrapper = mount(ProcessModeler, {
      props: { ready: true, definitionKey: 'leave', version: 2, xml: VALID_BPMN_XML, dirty: true, autoLoad: false },
    })
    expect(wrapper.find('[data-test="definition-key"]').text()).toContain('leave（v2）')
    expect(wrapper.find('[data-test="dirty"]').exists()).toBe(true)

    await wrapper.find('[data-test="palette-userTask"]').trigger('click')
    expect(wrapper.emitted('add-element')?.[0]).toEqual(['userTask'])

    await wrapper.find('[data-test="save-draft"]').trigger('click')
    expect(wrapper.emitted('save-draft')?.[0]).toEqual([VALID_BPMN_XML])
    await wrapper.find('[data-test="deploy"]').trigger('click')
    expect(wrapper.emitted('deploy')).toHaveLength(1)
    await wrapper.find('[data-test="validate"]').trigger('click')
    expect(wrapper.emitted('validate')?.[0]?.[0]).toMatchObject({ valid: true })
    await wrapper.find('[data-test="export"]').trigger('click')
    expect(wrapper.emitted('export')?.[0]).toEqual([VALID_BPMN_XML])

    await vi.dynamicImportSettled()
    await flushPromises()
    const canvas = wrapper.findComponent(ProcessCanvas)
    expect(canvas.exists()).toBe(true)
    expect(canvas.attributes('data-subpackage')).toBe('bpmn')

    canvas.vm.$emit('select', { id: 'tsk1', type: 'userTask', name: '主管审批' })
    await flushPromises()
    expect(wrapper.find('[data-test="properties-selected"]').text()).toContain('tsk1')
    expect(wrapper.emitted('select')?.[0]).toEqual([{ id: 'tsk1', type: 'userTask', name: '主管审批' }])

    canvas.vm.$emit('update:xml', '<bpmn:definitions next />')
    await flushPromises()
    expect(wrapper.emitted('update:xml')?.[0]).toEqual(['<bpmn:definitions next />'])
  })

  it('只读态禁用编辑与调板，仍可导出', () => {
    const wrapper = mount(ProcessModeler, {
      props: { ready: true, readOnly: true, xml: VALID_BPMN_XML, autoLoad: false },
    })
    expect(wrapper.find('[data-test="palette-userTask"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="save-draft"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="deploy"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="export"]').attributes('disabled')).toBeUndefined()
  })
})
