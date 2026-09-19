/**
 * 流程建模领域纯函数：BPMN 子集**零依赖**结构提取（元素 / 顺序流 / 扩展属性）、
 * 结构键与往返语义等价、结构校验（起止事件 / 唯一性 / 引用完整 / 孤立节点 / 子集合规）、
 * 属性 schema 与属性校验、版本推进、内容派生幂等键与错误码定位。
 *
 * 说明：**不依赖 bpmn-js / bpmn-moddle**（核心包依赖面为空）；强比对（`bpmn-moddle`）归 `ui-ep` 侧工具。
 * 属性**写回**经件层 bpmn-js `modeling.updateProperties`，本模块只做读取、校验与派生。
 */

import { fnv1aHex, stableStringify } from './serialize'

/** BPMN 子集元素类型（对齐工作流引擎可解析范围）。 */
export type ModelerElementType =
  | 'startEvent'
  | 'endEvent'
  | 'userTask'
  | 'exclusiveGateway'
  | 'parallelGateway'
  | 'sequenceFlow'

/** 建模阶段。 */
export type ModelerPhase = 'idle' | 'loading' | 'saving' | 'deploying' | 'validating' | 'done' | 'failed'

/** 校验结果来源。 */
export type ModelerValidateSource = 'structure' | 'engine'

/** 用户任务审批人来源。 */
export type ModelerAssigneeSource = 'subject-chain' | 'user' | 'dept' | 'initiator-manager' | 'form-field'

/** 多人规则（会签 / 或签）。 */
export type ModelerMultiRule = 'any' | 'all'

/** 属性控件取值形态。 */
export type ModelerPropertyKind = 'text' | 'select' | 'number' | 'switch' | 'expression'

/** 定义状态。 */
export type ModelerDefinitionStatus = 'draft' | 'published'

/** 建模元素运行态。 */
export interface ModelerElement {
  /** 元素标识。 */
  id: string
  /** 元素类型。 */
  type: ModelerElementType
  /** 元素名称。 */
  name?: string
}

/** 顺序流运行态。 */
export interface ModelerFlow {
  /** 流标识。 */
  id: string
  /** 起点元素标识。 */
  sourceRef: string
  /** 终点元素标识。 */
  targetRef: string
  /** 名称（展示于连线标签）。 */
  name?: string
  /** 条件表达式（网关出线）。 */
  condition?: string
  /** 是否默认流。 */
  default?: boolean
}

/** BPMN 结构（零依赖提取结果）。 */
export interface BpmnStructure {
  /** 元素集合（按 id 排序）。 */
  elements: ModelerElement[]
  /** 顺序流集合（按 id 排序）。 */
  flows: ModelerFlow[]
}

/** 校验错误。 */
export interface ModelerValidateError {
  /** 元素标识（可定位时给出）。 */
  elementId?: string
  /** 错误文案。 */
  message: string
}

/** 校验结果。 */
export interface ModelerValidateResult {
  /** 是否合法。 */
  valid: boolean
  /** 错误清单。 */
  errors: ModelerValidateError[]
  /** 结论来源。 */
  source: ModelerValidateSource
}

/** 节点属性值集合。 */
export interface ModelerElementProperties {
  /** 节点名称。 */
  name?: string
  /** 审批人来源。 */
  assigneeSource?: ModelerAssigneeSource
  /** 审批人取值（主体链标识 / 用户 / 部门 / 表单字段）。 */
  assigneeValue?: string
  /** 多人规则。 */
  multiRule?: ModelerMultiRule
  /** 超时数值。 */
  timeoutValue?: number
  /** 超时单位。 */
  timeoutUnit?: 'day' | 'hour'
  /** 是否发送通知。 */
  notify?: boolean
  /** 条件表达式（网关出线）。 */
  condition?: string
  /** 是否默认流。 */
  defaultFlow?: boolean
}

/** 属性项 schema。 */
export interface ModelerPropertyItem {
  /** 属性键。 */
  key: keyof ModelerElementProperties
  /** 展示名。 */
  label: string
  /** 控件形态。 */
  kind: ModelerPropertyKind
  /** 适用元素类型。 */
  appliesTo: ModelerElementType[]
  /** 选项（`select` 用）。 */
  options?: { value: string; label: string }[]
  /** 是否必填。 */
  required?: boolean
  /** 占位提示。 */
  placeholder?: string
}

/** 定义装载输入。 */
export interface ModelerDefinitionInput {
  /** 定义标识。 */
  definitionKey?: string
  /** 定义名称。 */
  name?: string
  /** 版本号。 */
  version?: number
  /** BPMN XML。 */
  xml?: string
  /** 定义状态。 */
  status?: ModelerDefinitionStatus
}

/** 定义运行态。 */
export interface ModelerDefinition {
  /** 定义标识。 */
  definitionKey: string
  /** 定义名称。 */
  name: string
  /** 版本号。 */
  version: number
  /** BPMN XML。 */
  xml: string
  /** 定义状态。 */
  status: ModelerDefinitionStatus
}

/** 提交结果。 */
export interface ModelerSubmitResult {
  /** 版本号。 */
  version?: number
  /** 定义标识。 */
  definitionKey?: string
  /** 提示文案。 */
  message?: string
}

/** 错误码定位处置。 */
export interface ModelerErrorTarget {
  /** 错误码。 */
  code: number
  /** 定位元素标识。 */
  elementId?: string
  /** i18n 文案键。 */
  i18nKey: string
  /** 是否重取定义。 */
  refresh: boolean
}

/** 定义与版本管理权限码。 */
export const MODELER_DEFINE_PERM = 'wf:define'

/** 占位文案（数据通路未就绪）。 */
export const MODELER_PLACEHOLDER_TEXT = '流程建模器未就绪（占位）'

/** 导入覆盖确认文案。 */
export const MODELER_IMPORT_CONFIRM_TEXT = '导入将覆盖当前画布内容，是否继续？'

/** BPMN 子集元素类型清单（调板顺序）。 */
export const MODELER_SUBSET: readonly ModelerElementType[] = [
  'startEvent',
  'endEvent',
  'userTask',
  'exclusiveGateway',
  'parallelGateway',
  'sequenceFlow',
]

/** 空流程模板（最小合法结构：开始 → 用户任务 → 结束）。 */
export const MODELER_BLANK_XML = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Definitions_blank" targetNamespace="http://bms.local/bpmn">',
  '  <bpmn:process id="Process_blank" isExecutable="true">',
  '    <bpmn:startEvent id="start_1" name="发起" />',
  '    <bpmn:userTask id="task_1" name="审批" />',
  '    <bpmn:endEvent id="end_1" name="结束" />',
  '    <bpmn:sequenceFlow id="flow_1" sourceRef="start_1" targetRef="task_1" />',
  '    <bpmn:sequenceFlow id="flow_2" sourceRef="task_1" targetRef="end_1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/** 元素标签 → 子集类型映射。 */
const ELEMENT_TAGS: Readonly<Record<string, ModelerElementType>> = {
  startEvent: 'startEvent',
  endEvent: 'endEvent',
  userTask: 'userTask',
  exclusiveGateway: 'exclusiveGateway',
  parallelGateway: 'parallelGateway',
}

/** 子集外的常见 BPMN 任务标签（用于「不支持的元素类型」定位）。 */
const UNSUPPORTED_TAGS: readonly string[] = [
  'serviceTask',
  'scriptTask',
  'manualTask',
  'businessRuleTask',
  'sendTask',
  'receiveTask',
  'callActivity',
  'subProcess',
  'boundaryEvent',
  'intermediateCatchEvent',
  'intermediateThrowEvent',
]

/** 审批人来源选项。 */
const ASSIGNEE_SOURCES: readonly { value: ModelerAssigneeSource; label: string }[] = [
  { value: 'subject-chain', label: '主体链（部门负责人 / 岗位 / 角色）' },
  { value: 'user', label: '指定用户' },
  { value: 'dept', label: '指定部门' },
  { value: 'initiator-manager', label: '发起人主管' },
  { value: 'form-field', label: '表单字段人员' },
]

/** 多人规则选项。 */
const MULTI_RULES: readonly { value: ModelerMultiRule; label: string }[] = [
  { value: 'all', label: '会签（全部同意方通过）' },
  { value: 'any', label: '或签（任一同意即通过）' },
]

/**
 * 构造校验结果。
 *
 * @param errors 错误清单。
 * @param source 结论来源。
 * @returns 校验结果。
 */
function result(errors: ModelerValidateError[], source: ModelerValidateSource = 'structure'): ModelerValidateResult {
  return { valid: errors.length === 0, errors, source }
}

/**
 * 提取标签（忽略命名空间前缀）。
 *
 * @param source XML 文本。
 * @param tag 标签名（不含前缀）。
 * @returns 标签匹配结果（属性原文）。
 */
function matchTags(source: string, tag: string): string[] {
  const pattern = new RegExp(`<(?:[A-Za-z0-9_]+:)?${tag}\\b([^>]*?)/?>`, 'g')
  const found: string[] = []
  let hit: RegExpExecArray | null = pattern.exec(source)
  while (hit !== null) {
    found.push(hit[1] ?? '')
    hit = pattern.exec(source)
  }
  return found
}

/**
 * 读取属性值（支持单双引号）。
 *
 * @param attrs 属性原文。
 * @param name 属性名。
 * @returns 属性值；不存在返回 `undefined`。
 */
function readAttr(attrs: string, name: string): string | undefined {
  const pattern = new RegExp(`(?:^|\\s)${name}\\s*=\\s*("([^"]*)"|'([^']*)')`)
  const hit = attrs.match(pattern)
  if (hit === null) {
    return undefined
  }
  return hit[2] ?? hit[3] ?? ''
}

/**
 * 读取元素标签内的属性原文（按元素 id 定位）。
 *
 * @param xml XML 文本。
 * @param elementId 元素标识。
 * @returns 属性原文；未命中返回 `undefined`。
 */
function attrsOfElement(xml: string, elementId: string): string | undefined {
  const source = String(xml ?? '')
  const tags = [...Object.keys(ELEMENT_TAGS), 'sequenceFlow', ...UNSUPPORTED_TAGS]
  for (const tag of tags) {
    for (const attrs of matchTags(source, tag)) {
      if (readAttr(attrs, 'id') === elementId) {
        return attrs
      }
    }
  }
  return undefined
}

/**
 * 提取 BPMN 子集结构（零依赖纯字符串解析；元素与流按 id 排序）。
 *
 * @param xml XML 文本。
 * @returns BPMN 结构。
 */
export function extractBpmnStructure(xml: string): BpmnStructure {
  const source = String(xml ?? '')
  const elements: ModelerElement[] = []
  for (const [tag, type] of Object.entries(ELEMENT_TAGS)) {
    for (const attrs of matchTags(source, tag)) {
      const id = readAttr(attrs, 'id')
      if (id === undefined || id === '') {
        continue
      }
      const rawName = readAttr(attrs, 'name')
      elements.push(rawName === undefined ? { id, type } : { id, type, name: rawName })
    }
  }
  const flows: ModelerFlow[] = []
  for (const attrs of matchTags(source, 'sequenceFlow')) {
    const id = readAttr(attrs, 'id')
    const sourceRef = readAttr(attrs, 'sourceRef')
    const targetRef = readAttr(attrs, 'targetRef')
    if (id === undefined || id === '' || sourceRef === undefined || targetRef === undefined) {
      continue
    }
    const flow: ModelerFlow = { id, sourceRef, targetRef }
    const name = readAttr(attrs, 'name')
    if (name !== undefined) {
      flow.name = name
    }
    const condition = readCondition(source, id)
    if (condition !== undefined) {
      flow.condition = condition
    }
    flows.push(flow)
  }
  // 默认流：`default` 属性出现在网关或流程上，值为顺序流 id。
  const defaultIds = new Set<string>()
  for (const tag of ['exclusiveGateway', 'parallelGateway']) {
    for (const attrs of matchTags(source, tag)) {
      const value = readAttr(attrs, 'default')
      if (value !== undefined && value !== '') {
        defaultIds.add(value)
      }
    }
  }
  for (const flow of flows) {
    if (defaultIds.has(flow.id)) {
      flow.default = true
    }
  }
  elements.sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0))
  flows.sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0))
  return { elements, flows }
}

/**
 * 读取顺序流条件表达式（`conditionExpression` 文本）。
 *
 * @param source XML 文本。
 * @param flowId 顺序流标识。
 * @returns 条件表达式；不存在返回 `undefined`。
 */
function readCondition(source: string, flowId: string): string | undefined {
  const block = new RegExp(
    `<(?:[A-Za-z0-9_]+:)?sequenceFlow\\b[^>]*id\\s*=\\s*["']${escapeRegExp(flowId)}["'][^>]*>([\\s\\S]*?)</(?:[A-Za-z0-9_]+:)?sequenceFlow>`,
  ).exec(source)
  if (block === null) {
    return undefined
  }
  const condition = /<(?:[A-Za-z0-9_]+:)?conditionExpression\b[^>]*>([\s\S]*?)<\/(?:[A-Za-z0-9_]+:)?conditionExpression>/.exec(
    block[1] ?? '',
  )
  if (condition === null) {
    return undefined
  }
  return decodeXmlText(condition[1] ?? '').trim()
}

/**
 * 转义正则元字符。
 *
 * @param value 原文。
 * @returns 转义文本。
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 还原 XML 文本实体（仅常见四项）。
 *
 * @param value 原文。
 * @returns 文本。
 */
function decodeXmlText(value: string): string {
  return String(value ?? '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&')
}

/**
 * 结构键（与命名空间前缀 / 属性顺序 / 空白无关）。
 *
 * @param structure BPMN 结构。
 * @returns 结构键。
 */
export function structureKey(structure: BpmnStructure): string {
  return stableStringify(structure)
}

/**
 * 判定两份 XML 是否结构等价（语义等价，忽略格式化差异）。
 *
 * @param left 左 XML。
 * @param right 右 XML。
 * @returns 是否等价。
 */
export function equivalentBpmnStructure(left: string, right: string): boolean {
  return structureKey(extractBpmnStructure(left)) === structureKey(extractBpmnStructure(right))
}

/**
 * 判定元素类型是否在 BPMN 子集内。
 *
 * @param type 元素类型文本。
 * @returns 是否在子集内。
 */
export function isSubsetElement(type: string): boolean {
  return Object.prototype.hasOwnProperty.call(ELEMENT_TAGS, type) || type === 'sequenceFlow'
}

/**
 * 读取元素类型（按元素标识）。
 *
 * @param xml XML 文本。
 * @param elementId 元素标识。
 * @returns 元素类型；未命中返回 `undefined`。
 */
export function elementTypeOf(xml: string, elementId: string): ModelerElementType | undefined {
  return extractBpmnStructure(xml).elements.find((element) => element.id === elementId)?.type
}

/**
 * 读取元素属性（用户任务 / 网关出线）。
 *
 * @param xml XML 文本。
 * @param elementId 元素标识。
 * @returns 属性值集合（未配置项省略）；未命中返回空对象。
 */
export function readElementProperties(xml: string, elementId: string): ModelerElementProperties {
  const attrs = attrsOfElement(xml, elementId)
  if (attrs === undefined) {
    return {}
  }
  const properties: ModelerElementProperties = {}
  const name = readAttr(attrs, 'name')
  if (name !== undefined && name !== '') {
    properties.name = name
  }
  const source = readAttr(attrs, 'bms:assigneeSource')
  if (source !== undefined && source !== '') {
    properties.assigneeSource = source as ModelerAssigneeSource
  }
  const value = readAttr(attrs, 'bms:assigneeValue')
  if (value !== undefined && value !== '') {
    properties.assigneeValue = value
  }
  const rule = readAttr(attrs, 'bms:multiRule')
  if (rule !== undefined && rule !== '') {
    properties.multiRule = rule as ModelerMultiRule
  }
  const timeout = readAttr(attrs, 'bms:timeoutValue')
  if (timeout !== undefined && timeout !== '' && Number.isFinite(Number(timeout))) {
    properties.timeoutValue = Number(timeout)
  }
  const unit = readAttr(attrs, 'bms:timeoutUnit')
  if (unit === 'day' || unit === 'hour') {
    properties.timeoutUnit = unit
  }
  const notify = readAttr(attrs, 'bms:notify')
  if (notify !== undefined) {
    properties.notify = notify === 'true'
  }
  const condition = readCondition(String(xml ?? ''), elementId)
  if (condition !== undefined && condition !== '') {
    properties.condition = condition
  }
  if (readAttr(attrs, 'default') !== undefined) {
    properties.defaultFlow = true
  }
  return properties
}

/**
 * 解析适用某元素类型的属性 schema。
 *
 * @param type 元素类型。
 * @returns 属性项清单。
 */
export function propertiesFor(type: ModelerElementType | undefined): ModelerPropertyItem[] {
  if (type === undefined) {
    return []
  }
  const items: ModelerPropertyItem[] = [
    { key: 'name', label: '节点名称', kind: 'text', appliesTo: [...MODELER_SUBSET], placeholder: '请输入节点名称' },
  ]
  if (type === 'userTask') {
    items.push(
      {
        key: 'assigneeSource',
        label: '审批人来源',
        kind: 'select',
        appliesTo: ['userTask'],
        options: ASSIGNEE_SOURCES.map((item) => ({ value: item.value, label: item.label })),
        required: true,
      },
      {
        key: 'assigneeValue',
        label: '审批人取值',
        kind: 'text',
        appliesTo: ['userTask'],
        required: true,
        placeholder: '主体链标识 / 用户 / 部门 / 表单字段',
      },
      {
        key: 'multiRule',
        label: '多人规则',
        kind: 'select',
        appliesTo: ['userTask'],
        options: MULTI_RULES.map((item) => ({ value: item.value, label: item.label })),
        required: true,
      },
      { key: 'timeoutValue', label: '超时', kind: 'number', appliesTo: ['userTask'], placeholder: '正整数' },
      {
        key: 'timeoutUnit',
        label: '超时单位',
        kind: 'select',
        appliesTo: ['userTask'],
        options: [
          { value: 'day', label: '天' },
          { value: 'hour', label: '小时' },
        ],
      },
      { key: 'notify', label: '待办通知', kind: 'switch', appliesTo: ['userTask'] },
    )
    return items
  }
  if (type === 'exclusiveGateway') {
    items.push(
      { key: 'condition', label: '条件表达式', kind: 'expression', appliesTo: ['exclusiveGateway'] },
      { key: 'defaultFlow', label: '默认流', kind: 'switch', appliesTo: ['exclusiveGateway'] },
    )
    return items
  }
  return items
}

/**
 * 属性面板全量 schema（供件层与核对页展示）。
 */
export const MODELER_PROPERTIES: readonly ModelerPropertyItem[] = [
  ...propertiesFor('userTask'),
  ...propertiesFor('exclusiveGateway').filter(
    (item) => !propertiesFor('userTask').some((exists) => exists.key === item.key),
  ),
]

/**
 * 校验节点属性（必填 / 枚举 / 正数 / 条件非空）。
 *
 * @param type 元素类型。
 * @param values 属性值集合。
 * @returns 校验结果。
 */
export function validateProperties(
  type: ModelerElementType | undefined,
  values: ModelerElementProperties,
): ModelerValidateResult {
  const errors: ModelerValidateError[] = []
  if (type === undefined) {
    return result(errors)
  }
  const name = String(values.name ?? '').trim()
  if (name === '') {
    errors.push({ message: '节点名称必填' })
  }
  if (type === 'userTask') {
    const source = values.assigneeSource
    if (source === undefined || !ASSIGNEE_SOURCES.some((item) => item.value === source)) {
      errors.push({ message: '审批人来源必填且在枚举内' })
    }
    if (String(values.assigneeValue ?? '').trim() === '') {
      errors.push({ message: '审批人取值必填' })
    }
    if (values.multiRule === undefined || !MULTI_RULES.some((item) => item.value === values.multiRule)) {
      errors.push({ message: '多人规则必填且在枚举内' })
    }
    if (values.timeoutValue !== undefined && !(values.timeoutValue > 0)) {
      errors.push({ message: '超时须为正数' })
    }
  }
  if (type === 'exclusiveGateway' && values.defaultFlow !== true && String(values.condition ?? '').trim() === '') {
    errors.push({ message: '非默认流须填写条件表达式' })
  }
  return result(errors)
}

/**
 * 校验 BPMN 结构（起止事件 / 唯一性 / 引用完整 / 孤立节点 / 子集合规）。
 *
 * @param xml XML 文本。
 * @returns 校验结果。
 */
export function validateBpmnStructure(xml: string): ModelerValidateResult {
  const source = String(xml ?? '')
  const errors: ModelerValidateError[] = []
  if (source.trim() === '') {
    return result([{ message: 'BPMN XML 为空' }])
  }
  const structure = extractBpmnStructure(source)

  // ① 子集外元素
  for (const tag of UNSUPPORTED_TAGS) {
    for (const attrs of matchTags(source, tag)) {
      const id = readAttr(attrs, 'id')
      errors.push(id === undefined ? { message: `不支持的元素类型：${tag}` } : { elementId: id, message: `不支持的元素类型：${tag}` })
    }
  }

  // ② 起止事件
  if (!structure.elements.some((element) => element.type === 'startEvent')) {
    errors.push({ message: '缺少开始事件' })
  }
  if (!structure.elements.some((element) => element.type === 'endEvent')) {
    errors.push({ message: '缺少结束事件' })
  }

  // ③ id 唯一
  const seen = new Set<string>()
  for (const item of [...structure.elements.map((element) => element.id), ...structure.flows.map((flow) => flow.id)]) {
    if (seen.has(item)) {
      errors.push({ elementId: item, message: '元素 / 流标识重复' })
    }
    seen.add(item)
  }

  // ④ 引用完整
  const elementIds = new Set(structure.elements.map((element) => element.id))
  for (const flow of structure.flows) {
    if (!elementIds.has(flow.sourceRef)) {
      errors.push({ elementId: flow.id, message: `顺序流起点不存在：${flow.sourceRef}` })
    }
    if (!elementIds.has(flow.targetRef)) {
      errors.push({ elementId: flow.id, message: `顺序流终点不存在：${flow.targetRef}` })
    }
  }

  // ⑤ 孤立节点（除开始事件须有入边、除结束事件须有出边）
  const hasIncoming = new Set(structure.flows.map((flow) => flow.targetRef))
  const hasOutgoing = new Set(structure.flows.map((flow) => flow.sourceRef))
  for (const element of structure.elements) {
    if (element.type !== 'startEvent' && !hasIncoming.has(element.id)) {
      errors.push({ elementId: element.id, message: '节点无入边（孤立节点）' })
    }
    if (element.type !== 'endEvent' && !hasOutgoing.has(element.id)) {
      errors.push({ elementId: element.id, message: '节点无出边（孤立节点）' })
    }
  }
  return result(errors)
}

/**
 * 合并前端结构校验与引擎预解析结论（任一不通过即不通过）。
 *
 * @param structure 前端结构校验结果。
 * @param engine 引擎预解析结果（未注入时省略）。
 * @returns 合并结果。
 */
export function mergeValidateResults(
  structure: ModelerValidateResult,
  engine?: ModelerValidateResult,
): ModelerValidateResult {
  if (engine === undefined) {
    return structure
  }
  return {
    valid: structure.valid && engine.valid,
    errors: [...structure.errors, ...engine.errors],
    source: 'engine',
  }
}

/**
 * 推进版本号（发布新版本）。
 *
 * @param version 当前版本。
 * @returns 下一版本（下界 1）。
 */
export function nextVersion(version: number): number {
  const base = Number.isFinite(version) ? Math.trunc(version) : 0
  return base < 0 ? 1 : base + 1
}

/**
 * 归一流程定义（XML 为空时回落空流程模板）。
 *
 * @param input 装载输入。
 * @returns 运行态定义。
 */
export function normalizeDefinition(input?: ModelerDefinitionInput): ModelerDefinition {
  const xml = String(input?.xml ?? '')
  return {
    definitionKey: String(input?.definitionKey ?? ''),
    name: String(input?.name ?? ''),
    version: Number.isFinite(input?.version) ? Math.trunc(input?.version as number) : 0,
    xml: xml.trim() === '' ? MODELER_BLANK_XML : xml,
    status: input?.status ?? 'draft',
  }
}

/**
 * 派生内容派生幂等键（同内容同键、内容变更换键）。
 *
 * @param definitionKey 定义标识。
 * @param version 版本号。
 * @param structure BPMN 结构。
 * @returns 幂等键（`wfd:{8 位十六进制}`）。
 */
export function deriveModelerKey(definitionKey: string, version: number, structure: BpmnStructure): string {
  const content = `${String(definitionKey ?? '')}:${version}:${structureKey(structure)}`
  return `wfd:${fnv1aHex(content)}`
}

/**
 * 从错误对象解析数值错误码。
 *
 * @param error 错误对象。
 * @returns 错误码；无则返回 `undefined`。
 */
export function resolveModelerErrorCode(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null) {
    return undefined
  }
  const code = (error as { code?: unknown }).code
  return typeof code === 'number' ? code : undefined
}

/**
 * 解析错误码定位（60006 定位元素 / 60007 定义级）。
 *
 * @param code 错误码。
 * @param structure 结构（可选，用于校正错误元素是否真实存在）。
 * @param elementId 后端给出的元素标识（可选）。
 * @returns 定位处置；未命中返回 `undefined`。
 */
export function resolveModelerErrorTarget(
  code: number | undefined,
  structure?: BpmnStructure,
  elementId?: string,
): ModelerErrorTarget | undefined {
  if (code === 60006) {
    const hit =
      elementId !== undefined &&
      elementId !== '' &&
      (structure === undefined || structure.elements.some((element) => element.id === elementId))
    return hit
      ? { code, elementId, i18nKey: 'error.60006', refresh: false }
      : { code, i18nKey: 'error.60006', refresh: false }
  }
  if (code === 60007) {
    return { code, i18nKey: 'error.60007', refresh: true }
  }
  return undefined
}
