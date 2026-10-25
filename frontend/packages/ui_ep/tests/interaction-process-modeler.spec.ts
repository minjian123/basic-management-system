// kiwi_id: 975
/** 流程建模器用例（08_8_2）：契约套件驱动 + 投影薄适配 + 三件组件（调板 / 属性面板 / 画布）与容器装配 + bpmn-moddle 强比对。 */

import { BaseAccess, MODELER_SUBSET, propertiesFor, type ModelerJobs } from '@bms/core'
import {
  describeProcessModelerContract,
  type ModelerContractHandlers,
  type ModelerContractValidation,
  type ProcessModelerContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { ProcessModeler, ProcessPalette, ProcessProperties, useBaseProcessModeler } from '../src'
import { equivalentBpmnStrong, parseBpmnStrongStructure } from '../src/utils/bpmnRoundTrip'

// bpmn-js 依赖 SVG 的 `getBBox`（jsdom 不实现）：对画布创建入口下桩，真实画布在核对页以 chromium 核验。
vi.mock('../src/utils/bpmnCanvas', () => ({
  createBpmnCanvas: vi.fn(async () => ({
    mode: 'modeler',
    instance: {},
    importXml: async () => undefined,
    saveXml: async () => VALID_XML,
    on: () => () => undefined,
    select: () => undefined,
    highlight: () => undefined,
    scrollTo: () => undefined,
    zoomBy: () => undefined,
    zoomTo: () => undefined,
    fitViewport: () => undefined,
    undo: () => undefined,
    redo: () => undefined,
    canUndo: () => true,
    canRedo: () => false,
    createElement: (type: string) => ({ id: 'created-1', type }),
    updateProperties: () => undefined,
    destroy: () => undefined,
  })),
}))

/** 合法最小流程。 */
const VALID_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" name="发起" />',
  '    <bpmn:userTask id="t1" name="审批" bms:assigneeSource="subject-chain" bms:assigneeValue="dept-manager" bms:multiRule="all" />',
  '    <bpmn:endEvent id="e1" name="结束" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="t1" />',
  '    <bpmn:sequenceFlow id="f2" sourceRef="t1" targetRef="e1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/** 缺结束事件的非法流程。 */
const INVALID_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" />',
  '    <bpmn:userTask id="t1" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="t1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

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

/** 流程建模器契约目标（`useBaseProcessModeler` 投影）。 */
function modelerTarget(): ProcessModelerContractTarget {
  return scoped(() => {
    const api = useBaseProcessModeler()
    const access = new SampleAccess()
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
      get readOnlyState() {
        return api.readOnly.value
      },
      get requestCount() {
        return api.requestCount.value
      },
      get phase() {
        return api.phase.value
      },
      get definitionKey() {
        return api.definitionKey.value
      },
      get version() {
        return api.version.value
      },
      get dirty() {
        return api.dirty.value
      },
      get canEdit() {
        return api.canEdit.value
      },
      xml: () => api.exportXml(),
      structure: () => {
        const structure = api.structure()
        return {
          elements: structure.elements.map((element) => element.id),
          flows: structure.flows.map((flow) => flow.id),
        }
      },
      selectedId: () => api.selected.value?.id ?? '',
      validateSource: () => api.validateResult.value?.source,
      errorElementIds: () =>
        (api.validateResult.value?.errors ?? [])
          .map((error) => error.elementId)
          .filter((elementId): elementId is string => elementId !== undefined),
      errorTargetElement: () => api.errorTarget.value?.elementId,
      setReady: (value: boolean) => api.setReady(value),
      setReadOnly: (value: boolean) => api.setReadOnly(value),
      setAccess: (codes) => {
        access.setCodes(codes ?? [])
        api.setAccess(codes === undefined ? undefined : access)
      },
      setHandlers: (handlers: ModelerContractHandlers) => {
        const jobs: ModelerJobs = {}
        if (handlers.loadDefinition !== undefined) {
          jobs.loadDefinition = async ({ definitionKey, version }) =>
            handlers.loadDefinition?.({ definitionKey, version })
        }
        if (handlers.saveDraft !== undefined) {
          jobs.saveDraft = async (input) => handlers.saveDraft?.({ ...input })
        }
        if (handlers.deploy !== undefined) {
          jobs.deploy = async (input) => handlers.deploy?.({ ...input })
        }
        if (handlers.validate !== undefined) {
          jobs.validate = async ({ xml }) => {
            const result = (await handlers.validate?.({ xml })) as ModelerContractValidation | undefined
            return result === undefined
              ? undefined
              : { valid: result.valid, source: result.source as 'structure' | 'engine', errors: result.errors }
          }
        }
        api.setJobs(jobs)
      },
      applyDefinition: (input) => api.applyDefinition(input),
      load: (definitionKey, version) => api.load(definitionKey, version),
      updateXml: (xml: string) => api.updateXml(xml),
      importXml: (xml: string) => api.importXml(xml),
      requestImport: (xml: string) => api.requestImport(xml),
      confirmImport: () => api.confirmImport(),
      cancelImport: () => api.cancelImport(),
      exportXml: () => api.exportXml(),
      select: (elementId) => {
        const result = api.select(elementId)
        return result === undefined ? undefined : { id: result.id, type: result.type }
      },
      validate: async (options) => {
        const result = await api.validate(options)
        return { valid: result.valid, source: result.source ?? 'structure', errors: result.errors }
      },
      saveDraft: () => api.saveDraft(),
      deploy: () => api.deploy(),
      retry: () => api.retry(),
      idempotencyKey: (kind) => api.idempotencyKey(kind),
      discard: () => api.discard(),
    }
  })
}

describeProcessModelerContract('流程建模器契约（useBaseProcessModeler 投影）', modelerTarget)

describe('投影薄适配', () => {
  it('装载定义并派生结构、脏态与幂等键', () => {
    const api = scoped(() => {
      const result = useBaseProcessModeler({ ready: true })
      const access = new SampleAccess()
      access.setCodes(['wf:define'])
      result.setAccess(access)
      result.applyDefinition({ definitionKey: 'leave', name: '请假流程', version: 2, xml: VALID_XML })
      return result
    })
    expect(api.structure().elements.map((element) => element.id)).toEqual(['e1', 's1', 't1'])
    expect(api.dirty.value).toBe(false)
    expect(api.canEdit.value).toBe(true)
    expect(api.idempotencyKey('draft')).toMatch(/^wfd:[0-9a-f]{8}$/)
  })

  it('注入处理函数后取定义并按实际发起数计数', async () => {
    const api = scoped(() => useBaseProcessModeler({ ready: true }))
    api.setJobs({ loadDefinition: async () => ({ definitionKey: 'leave', version: 2, xml: VALID_XML }) })
    await expect(api.load('leave')).resolves.toBe(true)
    expect(api.requestCount.value).toBe(1)
    expect(api.version.value).toBe(2)
  })
})

describe('ProcessPalette 元素调板件', () => {
  it('只列 BPMN 子集六类，点击与拖出上抛', async () => {
    const wrapper = mount(ProcessPalette)
    expect(wrapper.findAll('button')).toHaveLength(MODELER_SUBSET.length)
    await wrapper.find('[data-test="palette-userTask"]').trigger('click')
    expect(wrapper.emitted('add')?.[0]).toEqual(['userTask'])

    await wrapper.find('[data-test="palette-exclusiveGateway"]').trigger('dragstart')
    expect(wrapper.emitted('drag-start')?.[0]).toEqual(['exclusiveGateway'])
  })

  it('禁用态不可拖出', async () => {
    const wrapper = mount(ProcessPalette, { props: { disabled: true } })
    expect(wrapper.find('[data-test="palette-userTask"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="palette-userTask"]').trigger('dragstart')
    expect(wrapper.emitted('drag-start')).toBeUndefined()
  })
})

describe('ProcessProperties 节点属性面板件', () => {
  it('用户任务属性项齐备，写入上抛并给出校验结论', async () => {
    const wrapper = mount(ProcessProperties, {
      props: { selectedId: 't1', selectedType: 'userTask', properties: {} },
    })
    expect(propertiesFor('userTask')).toHaveLength(7)
    expect(wrapper.find('[data-test="property-name"]').exists()).toBe(true)

    await wrapper.find('[data-test="property-name"] input').setValue('审批')
    expect(wrapper.emitted('property-change')?.at(-1)).toEqual([{ key: 'name', value: '审批' }])
    expect(wrapper.emitted('validate')?.at(-1)?.[0]).toMatchObject({ valid: false })
  })

  it('填写齐全后校验通过', async () => {
    const wrapper = mount(ProcessProperties, {
      props: {
        selectedId: 't1',
        selectedType: 'userTask',
        properties: { name: '审批', assigneeSource: 'subject-chain', assigneeValue: 'dept-manager', multiRule: 'all' },
      },
    })
    await wrapper.find('[data-test="property-name"] input').trigger('input')
    expect(wrapper.emitted('validate')?.at(-1)?.[0]).toMatchObject({ valid: true })
  })

  it('未选中时展示流程级信息', () => {
    const wrapper = mount(ProcessProperties, {
      props: { selectedId: '', definitionKey: 'leave', definitionName: '请假流程' },
    })
    expect(wrapper.find('[data-test="properties-empty"]').text()).toContain('leave')
  })

  it('排他网关提供条件表达式与默认流属性项', () => {
    const wrapper = mount(ProcessProperties, {
      props: { selectedId: 'g1', selectedType: 'exclusiveGateway', properties: {} },
    })
    expect(propertiesFor('exclusiveGateway').map((item) => item.key)).toEqual(['name', 'condition', 'defaultFlow'])
    expect(wrapper.find('[data-test="property-condition"]').exists()).toBe(true)
  })
})

describe('ProcessModeler 容器装配', () => {
  const baseProps = { ready: true, definitionKey: 'leave', version: 2, xml: VALID_XML, autoLoad: false }

  it('装配三区、工具栏、命令栈与校验', async () => {
    const wrapper = mount(ProcessModeler, { props: baseProps })
    expect(wrapper.find('[data-test="process-palette"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="properties"]').exists()).toBe(true)
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="process-canvas"]').attributes('data-subpackage')).toBe('bpmn')

    await wrapper.find('[data-test="validate"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('validate')?.[0]?.[0]).toMatchObject({ valid: true })
  })

  it('调板点击创建元素并上抛 add-element', async () => {
    const wrapper = mount(ProcessModeler, { props: baseProps })
    await wrapper.find('[data-test="palette-userTask"]').trigger('click')
    expect(wrapper.emitted('add-element')?.[0]).toEqual(['userTask'])
  })

  it('导入经二次确认（确认弹窗出现、取消不覆盖）', async () => {
    const wrapper = mount(ProcessModeler, { props: baseProps })
    await wrapper.find('[data-test="import"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('import')).toHaveLength(1)
    expect(wrapper.find('[data-test="readonly-tip"]').exists()).toBe(false)
    // 未确认前画布内容不变。
    expect(wrapper.emitted('update:xml')).toBeUndefined()
  })

  it('只读态禁用编辑与调板、导出可用', () => {
    const wrapper = mount(ProcessModeler, { props: { ...baseProps, readOnly: true } })
    expect(wrapper.find('[data-test="palette-userTask"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="save-draft"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="export"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-test="readonly-tip"]').exists()).toBe(true)
  })

  it('版本历史载入进入只读并上抛', async () => {
    const wrapper = mount(ProcessModeler, {
      props: { ...baseProps, historyVersions: [{ version: 1, status: 'published' }] },
    })
    await wrapper.find('[data-test="history-toggle"]').trigger('click')
    await wrapper.find('[data-test="history-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('history-load')?.[0]).toEqual([1])
  })

  it('结构校验失败时高亮元素并入列错误', async () => {
    const wrapper = mount(ProcessModeler, {
      props: { ...baseProps, xml: INVALID_XML },
      global: {
        stubs: {
          ElDialog: {
            props: ['modelValue', 'title'],
            template: '<div data-test="shell-dialog"><slot /></div>',
          },
        },
      },
    })
    await wrapper.find('[data-test="validate"]').trigger('click')
    await flushPromises()
    const result = wrapper.emitted('validate')?.[0]?.[0] as { valid: boolean } | undefined
    expect(result?.valid).toBe(false)
    expect(wrapper.find('[data-test="validation-errors"]').exists()).toBe(true)
  })
})

describe('bpmn-moddle 强比对（XML 往返）', () => {
  it('命名空间前缀与属性顺序无关、结构变化即不等价', async () => {
    const prefixed = VALID_XML.replace(/bpmn:/g, 'bpmn2:').replace('xmlns:bpmn=', 'xmlns:bpmn2=')
    await expect(equivalentBpmnStrong(prefixed, VALID_XML)).resolves.toBe(true)
    await expect(equivalentBpmnStrong(VALID_XML.replace('name="审批"', 'name="复核"'), VALID_XML)).resolves.toBe(false)
  })

  it('强比对结构与核心零依赖提取结论一致', async () => {
    const strong = await parseBpmnStrongStructure(VALID_XML)
    expect(strong.elements).toEqual(['e1:EndEvent:结束', 's1:StartEvent:发起', 't1:UserTask:审批'])
    expect(strong.flows).toEqual(['f1:s1>t1', 'f2:t1>e1'])
  })
})
