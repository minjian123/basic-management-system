/**
 * 审批流展示领域纯函数：实例 / 节点 / 记录 / 待办归一、会签聚合、进度摘要、
 * 时间线排序与分组、意见折叠与校验、动作前置校验与可用矩阵、内容派生幂等键、
 * 错误码 → 处置映射、只读判定与只读图形态判定。
 *
 * 与 08-8-2 流程建模器共用的结构比对归 `domain/process-modeler.ts`；本篇不触 DOM、不发请求、不依赖渲染框架。
 * 说明：同意 / 驳回等动作的错误码与处置口径与《概要设计 · 工作流管理》「错误码与异常处理」节同源。
 */

import { fnv1aHex, stableStringify } from './serialize'

/** 节点状态。 */
export type ApprovalNodeStatus = 'done' | 'active' | 'pending' | 'rejected' | 'skipped'

/** 实例状态。 */
export type ApprovalInstanceStatus = 'running' | 'finished' | 'rejected' | 'abnormal'

/** 审批动作。 */
export type ApprovalAction = 'approve' | 'reject' | 'withdraw' | 'transfer' | 'comment'

/** 审批展示阶段。 */
export type ApprovalPhase = 'idle' | 'loading' | 'submitting' | 'done' | 'failed'

/** 取数分部状态（实例详情与审批记录各自独立结算）。 */
export type ApprovalPartState = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

/** 只读图形态。 */
export type ApprovalDiagramMode = 'xml' | 'image' | 'none' | 'failed'

/** 错误码处置类别。 */
export type ApprovalErrorHandling = 'denied' | 'stale' | 'duplicated' | 'signed-pending' | 'abnormal'

/** 时间线排序。 */
export type ApprovalTimelineOrder = 'asc' | 'desc'

/** 审批人。 */
export interface ApprovalAssignee {
  /** 用户标识。 */
  id: string
  /** 姓名。 */
  name: string
  /** 头像地址。 */
  avatar?: string
}

/** 审批附件。 */
export interface ApprovalAttachment {
  /** 附件标识。 */
  id: string
  /** 文件名。 */
  name: string
  /** 预览地址。 */
  url?: string
  /** 文件标识（预览件按此取址）。 */
  fileId?: string
  /** 文件大小（字节）。 */
  size?: number
}

/** 流程节点装载输入（后端可省略字段）。 */
export interface ApprovalNodeInput {
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  name: string
  /** 节点状态（缺省 `pending`）。 */
  status?: ApprovalNodeStatus
  /** 审批人。 */
  assignees?: readonly ApprovalAssignee[]
  /** 是否会签节点。 */
  signed?: boolean
  /** 会签已完成人数（缺省不派生）。 */
  signedDone?: number
  /** 会签总人数（缺省取审批人数）。 */
  signedTotal?: number
  /** 处理时间。 */
  time?: string
  /** 被驳回时指向的目标节点。 */
  rejectedTarget?: string
}

/** 流程节点运行态。 */
export interface ApprovalNode {
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  name: string
  /** 节点状态。 */
  status: ApprovalNodeStatus
  /** 审批人。 */
  assignees: ApprovalAssignee[]
  /** 是否会签节点。 */
  signed: boolean
  /** 会签已完成人数。 */
  signedDone?: number
  /** 会签总人数。 */
  signedTotal?: number
  /** 处理时间。 */
  time?: string
  /** 被驳回时指向的目标节点。 */
  rejectedTarget?: string
}

/** 流程实例装载输入。 */
export interface ApprovalInstanceInput {
  /** 实例标识。 */
  id: string
  /** 实例状态（缺省 `running`）。 */
  status?: ApprovalInstanceStatus
  /** 当前节点标识。 */
  currentNodeId?: string
  /** 节点序列。 */
  nodes?: readonly ApprovalNodeInput[]
  /** BPMN 定义快照（只读图数据源）。 */
  bpmnXml?: string
  /** 发起人标识。 */
  initiatorId?: string
  /** 发起人姓名。 */
  initiatorName?: string
  /** 业务类型。 */
  businessType?: string
  /** 业务单据标识。 */
  businessId?: string
  /** 启动时间。 */
  startedAt?: string
  /** 结束时间。 */
  finishedAt?: string
}

/** 流程实例运行态。 */
export interface ApprovalInstance {
  /** 实例标识。 */
  id: string
  /** 实例状态。 */
  status: ApprovalInstanceStatus
  /** 当前节点标识。 */
  currentNodeId?: string
  /** 节点序列。 */
  nodes: ApprovalNode[]
  /** BPMN 定义快照。 */
  bpmnXml: string
  /** 发起人标识。 */
  initiatorId?: string
  /** 发起人姓名。 */
  initiatorName?: string
  /** 业务类型。 */
  businessType?: string
  /** 业务单据标识。 */
  businessId?: string
  /** 启动时间。 */
  startedAt?: string
  /** 结束时间。 */
  finishedAt?: string
}

/** 审批记录装载输入。 */
export interface ApprovalRecordInput {
  /** 记录标识。 */
  id: string
  /** 节点标识。 */
  nodeId?: string
  /** 节点名称。 */
  nodeName?: string
  /** 审批人标识。 */
  assigneeId?: string
  /** 审批人姓名。 */
  assigneeName?: string
  /** 头像地址。 */
  avatar?: string
  /** 动作（缺省 `comment`）。 */
  action?: ApprovalAction
  /** 意见。 */
  comment?: string
  /** 附件。 */
  attachments?: readonly ApprovalAttachment[]
  /** 时间。 */
  createdAt?: string
  /** 驳回目标 / 转办对象展示名。 */
  target?: string
}

/** 审批记录运行态。 */
export interface ApprovalRecord {
  /** 记录标识。 */
  id: string
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  nodeName: string
  /** 审批人标识。 */
  assigneeId: string
  /** 审批人姓名。 */
  assigneeName: string
  /** 头像地址。 */
  avatar?: string
  /** 动作。 */
  action: ApprovalAction
  /** 意见。 */
  comment: string
  /** 附件。 */
  attachments: ApprovalAttachment[]
  /** 时间。 */
  createdAt: string
  /** 驳回目标 / 转办对象展示名。 */
  target?: string
}

/** 当前待办任务装载输入。 */
export interface ApprovalTaskInput {
  /** 任务标识。 */
  taskId?: string
  /** 节点标识。 */
  nodeId?: string
  /** 节点名称。 */
  nodeName?: string
  /** 是否会签。 */
  signed?: boolean
  /** 截止时间。 */
  deadline?: string
  /** 待处理审批人。 */
  assignees?: readonly ApprovalAssignee[]
}

/** 当前待办任务运行态。 */
export interface ApprovalTask {
  /** 任务标识。 */
  taskId: string
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  nodeName: string
  /** 是否会签。 */
  signed: boolean
  /** 截止时间。 */
  deadline?: string
  /** 待处理审批人。 */
  assignees: ApprovalAssignee[]
}

/** 提交载荷。 */
export interface ApprovalSubmitPayload {
  /** 动作。 */
  action: ApprovalAction
  /** 任务标识。 */
  taskId?: string
  /** 意见。 */
  comment?: string
  /** 驳回目标 / 转办对象。 */
  target?: string
  /** 幂等键（`Idempotency-Key`）。 */
  idempotencyKey: string
}

/** 提交结果。 */
export interface ApprovalSubmitResult {
  /** 实例标识。 */
  instanceId?: string
  /** 实例状态。 */
  status?: ApprovalInstanceStatus
  /** 当前节点标识。 */
  currentNodeId?: string
  /** 记录版本。 */
  recordVersion?: number
  /** 命中去重（60005）。 */
  duplicate?: boolean
  /** 提示文案。 */
  message?: string
}

/** 错误码处置映射项。 */
export interface ApprovalErrorHandlingItem {
  /** 处置类别。 */
  handling: ApprovalErrorHandling
  /** 是否重取实例状态。 */
  refresh: boolean
  /** i18n 文案键。 */
  i18nKey: string
  /** 是否使实例进入只读。 */
  readOnly?: boolean
}

/** 动作 / 意见校验结果。 */
export interface ApprovalCheckResult {
  /** 是否通过。 */
  valid: boolean
  /** 不通过文案。 */
  message: string
}

/** 会签进度。 */
export interface ApprovalSignProgress {
  /** 已完成人数。 */
  done: number
  /** 总人数。 */
  total: number
}

/** 进度摘要。 */
export interface ApprovalProgressSummary {
  /** 已完成节点数。 */
  done: number
  /** 节点总数。 */
  total: number
  /** 当前节点名称。 */
  activeName: string
}

/** 时间线节点分组。 */
export interface ApprovalRecordGroup {
  /** 节点标识（空节点标识归 `ungrouped`）。 */
  nodeId: string
  /** 节点名称。 */
  nodeName: string
  /** 记录集合。 */
  records: ApprovalRecord[]
}

/** 空节点标识分组键。 */
export const APPROVAL_UNGROUPED = 'ungrouped'

/** 审批写权限码。 */
export const APPROVAL_APPROVE_PERM = 'wf:approve'

/** 审批查权限码。 */
export const APPROVAL_QUERY_PERM = 'wf:query'

/** 审批意见长度上限（Unicode 码点；与后端 `len()` 同口径）。 */
export const APPROVAL_COMMENT_MAX = 4000

/** 长意见折叠阈值（Unicode 码点）。 */
export const APPROVAL_COMMENT_FOLD = 200

/** 占位文案（数据通路未就绪）。 */
export const APPROVAL_PLACEHOLDER_TEXT = '审批数据未就绪（占位）'

/** 空态文案。 */
export const APPROVAL_EMPTY_TEXT = '暂无审批记录'

/** 只读图降级文案。 */
export const APPROVAL_DIAGRAM_FALLBACK_TEXT = '流程图加载失败，已切换为进度视图'

/** 意见必填文案。 */
export const APPROVAL_COMMENT_REQUIRED_TEXT = '请填写审批意见'

/** 意见超长文案。 */
export const APPROVAL_COMMENT_TOO_LONG_TEXT = `审批意见超长（最多 ${APPROVAL_COMMENT_MAX} 字）`

/** 转办目标必填文案。 */
export const APPROVAL_TARGET_REQUIRED_TEXT = '请选择转办对象'

/** 无待办文案。 */
export const APPROVAL_NO_TASK_TEXT = '当前无待办任务'

/** 实例只读文案。 */
export const APPROVAL_READONLY_TEXT = '实例已结束或异常，仅供查看'

/** 重复提交按成功处理文案。 */
export const APPROVAL_DUPLICATE_TEXT = '该审批已处理，结果一致'

/** 动作中文名。 */
export const APPROVAL_ACTION_LABELS: Readonly<Record<ApprovalAction, string>> = {
  approve: '同意',
  reject: '驳回',
  withdraw: '撤回',
  transfer: '转办',
  comment: '评论',
}

/** 错误码 → 处置映射表（文案走 i18n `error.{code}`）。 */
export const APPROVAL_ERROR_HANDLERS: Readonly<Record<number, ApprovalErrorHandlingItem>> = {
  60003: { handling: 'denied', refresh: true, i18nKey: 'error.60003' },
  60004: { handling: 'stale', refresh: true, i18nKey: 'error.60004' },
  60005: { handling: 'duplicated', refresh: true, i18nKey: 'error.60005' },
  60008: { handling: 'signed-pending', refresh: true, i18nKey: 'error.60008' },
  60009: { handling: 'abnormal', refresh: true, i18nKey: 'error.60009', readOnly: true },
}

/** 校验通过结果。 */
const OK: ApprovalCheckResult = { valid: true, message: '' }

/**
 * 构造校验失败结果。
 *
 * @param message 失败文案。
 * @returns 校验结果。
 */
function fail(message: string): ApprovalCheckResult {
  return { valid: false, message }
}

/**
 * 统计 Unicode 码点数（`Array.from` 逐个码点；中文与 emoji 均按 1 计）。
 *
 * @param value 待统计文本。
 * @returns 码点数。
 */
export function countCodePoints(value: string): number {
  return Array.from(String(value ?? '')).length
}

/**
 * 归一审批人（缺省字段补齐）。
 *
 * @param input 装载输入。
 * @returns 运行态审批人。
 */
export function normalizeAssignee(input: ApprovalAssignee): ApprovalAssignee {
  return {
    id: String(input?.id ?? ''),
    name: String(input?.name ?? ''),
    avatar: input?.avatar,
  }
}

/**
 * 归一审批人集合。
 *
 * @param input 装载输入。
 * @returns 运行态审批人集合。
 */
export function normalizeAssignees(input?: readonly ApprovalAssignee[]): ApprovalAssignee[] {
  return (input ?? []).map((item) => normalizeAssignee(item))
}

/**
 * 归一流程节点（状态缺省 `pending`）。
 *
 * @param input 装载输入。
 * @returns 运行态节点。
 */
export function normalizeNode(input: ApprovalNodeInput): ApprovalNode {
  return {
    nodeId: String(input?.nodeId ?? ''),
    name: String(input?.name ?? ''),
    status: input?.status ?? 'pending',
    assignees: normalizeAssignees(input?.assignees),
    signed: input?.signed === true,
    signedDone: input?.signedDone,
    signedTotal: input?.signedTotal,
    time: input?.time,
    rejectedTarget: input?.rejectedTarget,
  }
}

/**
 * 归一节点序列。
 *
 * @param input 装载输入。
 * @returns 运行态节点序列。
 */
export function normalizeNodes(input?: readonly ApprovalNodeInput[]): ApprovalNode[] {
  return (input ?? []).map((item) => normalizeNode(item))
}

/**
 * 归一流程实例（BPMN 快照缺省空串）。
 *
 * @param input 装载输入。
 * @returns 运行态实例。
 */
export function normalizeInstance(input: ApprovalInstanceInput): ApprovalInstance {
  return {
    id: String(input?.id ?? ''),
    status: input?.status ?? 'running',
    currentNodeId: input?.currentNodeId,
    nodes: normalizeNodes(input?.nodes),
    bpmnXml: String(input?.bpmnXml ?? ''),
    initiatorId: input?.initiatorId,
    initiatorName: input?.initiatorName,
    businessType: input?.businessType,
    businessId: input?.businessId,
    startedAt: input?.startedAt,
    finishedAt: input?.finishedAt,
  }
}

/**
 * 归一审批记录（动作缺省 `comment`）。
 *
 * @param input 装载输入。
 * @returns 运行态记录。
 */
export function normalizeRecord(input: ApprovalRecordInput): ApprovalRecord {
  return {
    id: String(input?.id ?? ''),
    nodeId: String(input?.nodeId ?? ''),
    nodeName: String(input?.nodeName ?? ''),
    assigneeId: String(input?.assigneeId ?? ''),
    assigneeName: String(input?.assigneeName ?? ''),
    avatar: input?.avatar,
    action: input?.action ?? 'comment',
    comment: String(input?.comment ?? ''),
    attachments: (input?.attachments ?? []).map((item) => ({ ...item })),
    createdAt: String(input?.createdAt ?? ''),
    target: input?.target,
  }
}

/**
 * 归一审批记录集合。
 *
 * @param input 装载输入。
 * @returns 运行态记录集合。
 */
export function normalizeRecords(input?: readonly ApprovalRecordInput[]): ApprovalRecord[] {
  return (input ?? []).map((item) => normalizeRecord(item))
}

/**
 * 归一当前待办任务（缺省返回 `undefined`）。
 *
 * @param input 装载输入。
 * @returns 运行态待办；无任务标识时返回 `undefined`。
 */
export function normalizeTask(input?: ApprovalTaskInput): ApprovalTask | undefined {
  if (input === undefined || String(input.taskId ?? '') === '') {
    return undefined
  }
  return {
    taskId: String(input.taskId),
    nodeId: String(input.nodeId ?? ''),
    nodeName: String(input.nodeName ?? ''),
    signed: input.signed === true,
    deadline: input.deadline,
    assignees: normalizeAssignees(input.assignees),
  }
}

/**
 * 解析当前节点索引（命中 `currentNodeId` 优先，否则取首个 `active`）。
 *
 * @param nodes 节点序列。
 * @param currentNodeId 当前节点标识。
 * @returns 索引；皆无时返回 `-1`。
 */
export function resolveActiveNodeIndex(nodes: readonly ApprovalNode[], currentNodeId?: string): number {
  if (currentNodeId !== undefined && currentNodeId !== '') {
    const hit = nodes.findIndex((node) => node.nodeId === currentNodeId)
    if (hit >= 0) {
      return hit
    }
  }
  return nodes.findIndex((node) => node.status === 'active')
}

/**
 * 解析进度件可见节点（分支降级：紧凑省略未走分支，非紧凑置灰保留一行）。
 *
 * @param nodes 节点序列。
 * @param options 选项（`compact` 紧凑模式）。
 * @returns 可见节点序列。
 */
export function resolveVisibleNodes(
  nodes: readonly ApprovalNode[],
  options: { compact?: boolean } = {},
): ApprovalNode[] {
  if (options.compact === true) {
    return nodes.filter((node) => node.status !== 'pending')
  }
  return nodes.map((node) => (node.status === 'pending' ? { ...node, status: 'skipped' } : node))
}

/**
 * 解析会签进度（非会签节点返回 `undefined`）。
 *
 * @param node 节点。
 * @returns 会签进度；非会签返回 `undefined`。
 */
export function signProgress(node: ApprovalNode): ApprovalSignProgress | undefined {
  if (!node.signed) {
    return undefined
  }
  const total = node.signedTotal ?? node.assignees.length
  return { done: node.signedDone ?? 0, total }
}

/**
 * 解析进度摘要（已完成节点数 / 节点总数 / 当前节点名称）。
 *
 * @param instance 流程实例。
 * @returns 进度摘要。
 */
export function resolveProgressSummary(instance: ApprovalInstance): ApprovalProgressSummary {
  const done = instance.nodes.filter((node) => node.status === 'done').length
  const index = resolveActiveNodeIndex(instance.nodes, instance.currentNodeId)
  return {
    done,
    total: instance.nodes.length,
    activeName: index < 0 ? '' : instance.nodes[index].name,
  }
}

/**
 * 判定实例是否只读（已结束 / 已驳回 / 异常）。
 *
 * @param status 实例状态。
 * @returns 是否只读。
 */
export function resolveReadonlyInstance(status: ApprovalInstanceStatus | undefined): boolean {
  return status === 'finished' || status === 'rejected' || status === 'abnormal'
}

/**
 * 时间线排序（缺省正序；倒序保持同时间稳定序）。
 *
 * @param records 记录集合。
 * @param order 排序方向（缺省 `asc`）。
 * @returns 排序后记录集合。
 */
export function resolveTimelineOrderRecords(
  records: readonly ApprovalRecord[],
  order: ApprovalTimelineOrder = 'asc',
): ApprovalRecord[] {
  if (order === 'asc') {
    return [...records]
  }
  return records
    .map((record, index) => ({ record, index }))
    .sort((left, right) => {
      if (left.record.createdAt === right.record.createdAt) {
        return right.index - left.index
      }
      return left.record.createdAt < right.record.createdAt ? 1 : -1
    })
    .map((item) => item.record)
}

/**
 * 按节点分组审批记录（按记录出现顺序；空节点标识归 `ungrouped`）。
 *
 * @param records 记录集合。
 * @returns 分组集合。
 */
export function groupRecordsByNode(records: readonly ApprovalRecord[]): ApprovalRecordGroup[] {
  const groups: ApprovalRecordGroup[] = []
  const index = new Map<string, number>()
  for (const record of records) {
    const key = record.nodeId === '' ? APPROVAL_UNGROUPED : record.nodeId
    const found = index.get(key)
    if (found === undefined) {
      index.set(key, groups.length)
      groups.push({
        nodeId: key,
        nodeName: record.nodeName === '' ? APPROVAL_UNGROUPED : record.nodeName,
        records: [record],
      })
      continue
    }
    groups[found].records.push(record)
    if (groups[found].nodeName === APPROVAL_UNGROUPED && record.nodeName !== '') {
      groups[found].nodeName = record.nodeName
    }
  }
  return groups
}

/**
 * 折叠长意见（按 Unicode 码点截断）。
 *
 * @param comment 意见。
 * @param limit 折叠阈值（缺省 200 码点）。
 * @returns 展示文本与是否已折叠。
 */
export function foldComment(comment: string, limit: number = APPROVAL_COMMENT_FOLD): { text: string; folded: boolean } {
  const points = Array.from(String(comment ?? ''))
  if (points.length <= limit) {
    return { text: String(comment ?? ''), folded: false }
  }
  return { text: points.slice(0, limit).join(''), folded: true }
}

/**
 * 校验审批意见（必填与长度上限，按码点计）。
 *
 * @param comment 意见。
 * @param options 选项（`required` 是否必填）。
 * @returns 校验结果。
 */
export function validateComment(comment: string, options: { required?: boolean } = {}): ApprovalCheckResult {
  const value = String(comment ?? '')
  if (options.required === true && value.trim() === '') {
    return fail(APPROVAL_COMMENT_REQUIRED_TEXT)
  }
  return countCodePoints(value) > APPROVAL_COMMENT_MAX ? fail(APPROVAL_COMMENT_TOO_LONG_TEXT) : OK
}

/**
 * 校验目标（驳回退回节点 / 转办对象）。
 *
 * @param target 目标。
 * @param options 选项（`required` 是否必填）。
 * @returns 校验结果。
 */
export function validateTarget(target: string | undefined, options: { required?: boolean } = {}): ApprovalCheckResult {
  if (options.required === true && String(target ?? '').trim() === '') {
    return fail(APPROVAL_TARGET_REQUIRED_TEXT)
  }
  return OK
}

/**
 * 校验动作前置条件（意见必填 / 目标必填 / 动作可用）。
 *
 * @param action 动作。
 * @param input 入参（意见、目标、可审批、可撤回）。
 * @returns 校验结果。
 */
export function validateAction(
  action: ApprovalAction,
  input: {
    /** 意见。 */
    comment?: string
    /** 目标。 */
    target?: string
    /** 可审批。 */
    canApprove?: boolean
    /** 可撤回。 */
    canWithdraw?: boolean
    /** 是否有当前待办。 */
    hasTask?: boolean
  } = {},
): ApprovalCheckResult {
  const hasTask = input.hasTask !== false
  if (action === 'withdraw') {
    if (input.canWithdraw !== true) {
      return fail(APPROVAL_NO_TASK_TEXT)
    }
    return validateComment(String(input.comment ?? ''), { required: false })
  }
  if (!hasTask || input.canApprove !== true) {
    return fail(APPROVAL_NO_TASK_TEXT)
  }
  switch (action) {
    case 'reject':
      return validateComment(String(input.comment ?? ''), { required: true })
    case 'transfer':
      return validateTarget(input.target, { required: true })
    case 'comment':
      return validateComment(String(input.comment ?? ''), { required: true })
    default:
      return validateComment(String(input.comment ?? ''), { required: false })
  }
}

/**
 * 解析可用动作矩阵（异常实例全部不可用；撤回按发起人判定独立）。
 *
 * @param context 上下文（实例状态、可审批、可撤回、是否有当前待办）。
 * @returns 各动作是否可用。
 */
export function resolveApprovalActions(context: {
  /** 实例状态。 */
  status?: ApprovalInstanceStatus
  /** 可审批。 */
  canApprove?: boolean
  /** 可撤回。 */
  canWithdraw?: boolean
  /** 是否有当前待办。 */
  hasTask?: boolean
  /** 当前任务标识。 */
  taskId?: string
}): { approve: boolean; reject: boolean; transfer: boolean; withdraw: boolean; comment: boolean } {
  const running = (context.status ?? 'running') === 'running'
  const task = running && context.hasTask === true && context.canApprove === true
  return {
    approve: task,
    reject: task,
    transfer: task,
    withdraw: running && context.canWithdraw === true,
    comment: task,
  }
}

/**
 * 派生内容派生幂等键（同内容同键、内容变更换键）。
 *
 * @param taskId 任务标识。
 * @param action 动作。
 * @param comment 意见。
 * @param target 目标。
 * @returns 幂等键（`wf:{8 位十六进制}`）。
 */
export function deriveApprovalKey(
  taskId: string | undefined,
  action: ApprovalAction,
  comment?: string,
  target?: string,
): string {
  const content = {
    taskId: String(taskId ?? ''),
    action,
    comment: String(comment ?? '').trim(),
    target: String(target ?? ''),
  }
  return `wf:${fnv1aHex(stableStringify(content))}`
}

/**
 * 解析只读图形态（三级判定：失败 → XML → 图片 → 无）。
 *
 * @param input 入参（BPMN XML、图片地址、是否已失败）。
 * @returns 只读图形态。
 */
export function resolveDiagramMode(input: {
  /** BPMN 定义快照。 */
  bpmnXml?: string
  /** 图片地址（预签名通路）。 */
  url?: string
  /** 是否已失败（依赖加载或 XML 解析失败）。 */
  failed?: boolean
}): ApprovalDiagramMode {
  if (input.failed === true) {
    return 'failed'
  }
  if (String(input.bpmnXml ?? '') !== '') {
    return 'xml'
  }
  return String(input.url ?? '') !== '' ? 'image' : 'none'
}

/**
 * 从错误对象解析数值错误码（审批侧命名，避开 `domain/permission-config` 同名导出）。
 *
 * @param error 错误对象。
 * @returns 错误码；无则返回 `undefined`。
 */
export function resolveApprovalErrorCode(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null) {
    return undefined
  }
  const code = (error as { code?: unknown }).code
  return typeof code === 'number' ? code : undefined
}

/**
 * 查错误码处置映射。
 *
 * @param code 错误码。
 * @returns 处置项；未命中返回 `undefined`。
 */
export function resolveErrorHandling(code: number | undefined): ApprovalErrorHandlingItem | undefined {
  return code === undefined ? undefined : APPROVAL_ERROR_HANDLERS[code]
}
