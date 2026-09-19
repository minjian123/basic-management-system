/** 流程建模领域纯函数用例（`08-8-2`）：结构提取 / 结构键与往返等价 / 结构校验 / 属性 schema 与校验 / 版本 / 幂等键 / 错误码定位。 */

import { describe, expect, it } from 'vitest'

import {
  deriveModelerKey,
  elementTypeOf,
  equivalentBpmnStructure,
  extractBpmnStructure,
  isSubsetElement,
  mergeValidateResults,
  MODELER_BLANK_XML,
  MODELER_SUBSET,
  nextVersion,
  normalizeDefinition,
  propertiesFor,
  readElementProperties,
  resolveModelerErrorCode,
  resolveModelerErrorTarget,
  structureKey,
  validateBpmnStructure,
  validateProperties,
} from '../src'

/** 合法最小流程。 */
const VALID_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" name="发起" />',
  '    <bpmn:userTask id="t1" name="审批" bms:assigneeSource="subject-chain" bms:assigneeValue="dept-manager" bms:multiRule="all" bms:timeoutValue="2" bms:timeoutUnit="day" bms:notify="true" />',
  '    <bpmn:endEvent id="e1" name="结束" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="t1" />',
  '    <bpmn:sequenceFlow id="f2" sourceRef="t1" targetRef="e1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/** 带排他网关与条件的流程。 */
const GATEWAY_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" />',
  '    <bpmn:exclusiveGateway id="g1" default="f4" />',
  '    <bpmn:userTask id="t1" />',
  '    <bpmn:endEvent id="e1" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="g1" />',
  '    <bpmn:sequenceFlow id="f2" sourceRef="g1" targetRef="t1"><bpmn:conditionExpression>amount &gt; 1000</bpmn:conditionExpression></bpmn:sequenceFlow>',
  '    <bpmn:sequenceFlow id="f3" sourceRef="t1" targetRef="e1" />',
  '    <bpmn:sequenceFlow id="f4" sourceRef="g1" targetRef="e1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

describe('结构提取', () => {
  it('提取元素与顺序流（忽略命名空间前缀），按 id 排序', () => {
    const structure = extractBpmnStructure(VALID_XML)
    expect(structure.elements.map((element) => element.id)).toEqual(['e1', 's1', 't1'])
    expect(structure.elements.map((element) => element.type)).toEqual(['endEvent', 'startEvent', 'userTask'])
    expect(structure.flows.map((flow) => flow.id)).toEqual(['f1', 'f2'])
    expect(structure.flows[0]).toMatchObject({ sourceRef: 's1', targetRef: 't1' })
  })

  it('提取条件表达式（实体还原）与默认流', () => {
    const structure = extractBpmnStructure(GATEWAY_XML)
    const conditional = structure.flows.find((flow) => flow.id === 'f2')
    expect(conditional?.condition).toBe('amount > 1000')
    expect(structure.flows.find((flow) => flow.id === 'f4')?.default).toBe(true)
  })

  it('元素类型查询与子集判定', () => {
    expect(elementTypeOf(VALID_XML, 't1')).toBe('userTask')
    expect(elementTypeOf(VALID_XML, 'absent')).toBeUndefined()
    expect(isSubsetElement('userTask')).toBe(true)
    expect(isSubsetElement('sequenceFlow')).toBe(true)
    expect(isSubsetElement('serviceTask')).toBe(false)
    expect(MODELER_SUBSET).toHaveLength(6)
  })
})

describe('结构键与往返等价', () => {
  it('结构键与命名空间前缀 / 属性顺序 / 空白无关', () => {
    const reformatted = VALID_XML.replace(/\n\s*/g, '\n          ').replace(
      'id="s1" name="发起"',
      'name="发起" id="s1"',
    )
    const prefixed = VALID_XML.replace(/bpmn:/g, 'bpmn2:').replace(
      'xmlns:bpmn=',
      'xmlns:bpmn2=',
    )
    expect(structureKey(extractBpmnStructure(reformatted))).toBe(structureKey(extractBpmnStructure(VALID_XML)))
    expect(equivalentBpmnStructure(prefixed, VALID_XML)).toBe(true)
  })

  it('结构变化即不等价', () => {
    expect(equivalentBpmnStructure(VALID_XML.replace('name="审批"', 'name="复核"'), VALID_XML)).toBe(false)
  })
})

describe('结构校验', () => {
  it('合法流程通过', () => {
    const result = validateBpmnStructure(VALID_XML)
    expect(result.valid).toBe(true)
    expect(result.errors).toEqual([])
    expect(result.source).toBe('structure')
  })

  it('空 XML 报错', () => {
    expect(validateBpmnStructure('   ').valid).toBe(false)
  })

  it('缺开始 / 结束事件可定位', () => {
    const noEnd = VALID_XML.replace('<bpmn:endEvent id="e1" name="结束" />', '')
    const result = validateBpmnStructure(noEnd)
    expect(result.valid).toBe(false)
    expect(result.errors.some((error) => error.message.includes('缺少结束事件'))).toBe(true)
  })

  it('孤立节点与悬空引用可定位', () => {
    const orphan = VALID_XML.replace('<bpmn:sequenceFlow id="f2" sourceRef="t1" targetRef="e1" />', '')
    const result = validateBpmnStructure(orphan)
    expect(result.valid).toBe(false)
    expect(result.errors.some((error) => error.elementId === 'e1')).toBe(true)

    const dangling = VALID_XML.replace('targetRef="t1"', 'targetRef="absent"')
    expect(
      validateBpmnStructure(dangling).errors.some((error) => error.message.includes('顺序流终点不存在')),
    ).toBe(true)
  })

  it('重复 id 与非子集元素可定位', () => {
    const duplicated = VALID_XML.replace('id="e1"', 'id="t1"')
    expect(validateBpmnStructure(duplicated).errors.some((error) => error.message.includes('重复'))).toBe(true)

    const unsupported = VALID_XML.replace('<bpmn:userTask', '<bpmn:serviceTask')
    const result = validateBpmnStructure(unsupported)
    expect(result.valid).toBe(false)
    expect(result.errors.some((error) => error.message.includes('不支持的元素类型'))).toBe(true)
  })

  it('校验合并：未注入引擎返回结构结论，注入后来源为 engine', () => {
    const structure = validateBpmnStructure(VALID_XML)
    expect(mergeValidateResults(structure)).toBe(structure)

    const merged = mergeValidateResults(structure, {
      valid: false,
      errors: [{ elementId: 't1', message: '引擎不可解析' }],
      source: 'engine',
    })
    expect(merged.valid).toBe(false)
    expect(merged.source).toBe('engine')
    expect(merged.errors).toHaveLength(1)
  })
})

describe('属性 schema / 读取与校验', () => {
  it('用户任务属性项齐备，网关出线含条件与默认流', () => {
    const userTask = propertiesFor('userTask').map((item) => item.key)
    expect(userTask).toEqual([
      'name',
      'assigneeSource',
      'assigneeValue',
      'multiRule',
      'timeoutValue',
      'timeoutUnit',
      'notify',
    ])
    expect(propertiesFor('exclusiveGateway').map((item) => item.key)).toEqual(['name', 'condition', 'defaultFlow'])
    expect(propertiesFor(undefined)).toEqual([])
  })

  it('读取元素属性（扩展属性与默认流）', () => {
    expect(readElementProperties(VALID_XML, 't1')).toEqual({
      name: '审批',
      assigneeSource: 'subject-chain',
      assigneeValue: 'dept-manager',
      multiRule: 'all',
      timeoutValue: 2,
      timeoutUnit: 'day',
      notify: true,
    })
    expect(readElementProperties(GATEWAY_XML, 'g1')).toMatchObject({ defaultFlow: true })
    expect(readElementProperties(GATEWAY_XML, 'f2')).toMatchObject({ condition: 'amount > 1000' })
    expect(readElementProperties(VALID_XML, 'absent')).toEqual({})
  })

  it('属性校验：必填 / 枚举 / 正数 / 条件非空', () => {
    expect(validateProperties('userTask', {}).valid).toBe(false)
    expect(
      validateProperties('userTask', {
        name: '审批',
        assigneeSource: 'subject-chain',
        assigneeValue: 'dept-manager',
        multiRule: 'all',
      }).valid,
    ).toBe(true)

    const badRule = validateProperties('userTask', {
      name: '审批',
      assigneeSource: 'subject-chain',
      assigneeValue: 'x',
      multiRule: 'both' as never,
    })
    expect(badRule.valid).toBe(false)

    expect(validateProperties('userTask', { name: 'n', timeoutValue: 0 }).valid).toBe(false)
    expect(validateProperties('exclusiveGateway', { name: 'g' }).valid).toBe(false)
    expect(validateProperties('exclusiveGateway', { name: 'g', defaultFlow: true }).valid).toBe(true)
  })
})

describe('版本 / 定义 / 幂等键 / 错误码', () => {
  it('版本推进与定义归一（XML 空回落模板）', () => {
    expect(nextVersion(0)).toBe(1)
    expect(nextVersion(2)).toBe(3)
    expect(normalizeDefinition().xml).toBe(MODELER_BLANK_XML)
    expect(normalizeDefinition({ definitionKey: 'leave', version: 2 }).status).toBe('draft')
  })

  it('幂等键：同内容同键、版本或结构变更换键', () => {
    const structure = extractBpmnStructure(VALID_XML)
    const base = deriveModelerKey('leave', 2, structure)
    expect(base).toBe(deriveModelerKey('leave', 2, extractBpmnStructure(VALID_XML)))
    expect(base).not.toBe(deriveModelerKey('leave', 3, structure))
    expect(base).not.toBe(deriveModelerKey('leave', 2, extractBpmnStructure(GATEWAY_XML)))
    expect(base).toMatch(/^wfd:[0-9a-f]{8}$/)
  })

  it('错误码定位：60006 带元素 / 60007 定义级 / 未命中 undefined', () => {
    expect(resolveModelerErrorCode(Object.assign(new Error('x'), { code: 60006 }))).toBe(60006)
    expect(resolveModelerErrorCode(new Error('x'))).toBeUndefined()

    const structure = extractBpmnStructure(VALID_XML)
    expect(resolveModelerErrorTarget(60006, structure, 't1')).toMatchObject({ code: 60006, elementId: 't1' })
    expect(resolveModelerErrorTarget(60006, structure, 'absent')?.elementId).toBeUndefined()
    expect(resolveModelerErrorTarget(60007, structure)).toMatchObject({ code: 60007, refresh: true })
    expect(resolveModelerErrorTarget(99999, structure)).toBeUndefined()
  })
})
