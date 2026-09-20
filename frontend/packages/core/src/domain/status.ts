/**
 * 领域纯函数：状态语义色（三层取色 + 内置映射 + 令牌名）。
 *
 * 不触 DOM、不请求；颜色一律输出设计令牌变量名（`--bms-color-*`），不硬编码色值。
 */

/** 语义色档位。 */
export type StatusSemantic = 'success' | 'warning' | 'danger' | 'info' | 'primary'

/** 语义色五档（顺序即取色优先级展示顺序）。 */
export const STATUS_SEMANTICS: readonly StatusSemantic[] = ['success', 'warning', 'danger', 'info', 'primary']

/** 语义色 → 设计令牌变量名。 */
export const STATUS_SEMANTIC_TOKENS: Readonly<Record<StatusSemantic, string>> = {
  success: '--bms-color-success',
  warning: '--bms-color-warning',
  danger: '--bms-color-danger',
  info: '--bms-color-info',
  primary: '--bms-color-primary',
}

/** 兜底语义色（未命中任何层）。 */
export const STATUS_FALLBACK_SEMANTIC: StatusSemantic = 'info'

/** 内置语义映射（键为小写归一后的值）。 */
export const STATUS_BUILTIN_MAP: Readonly<Record<string, StatusSemantic>> = {
  enabled: 'success',
  normal: 'success',
  active: 'success',
  approved: 'success',
  passed: 'success',
  finished: 'success',
  启用: 'success',
  正常: 'success',
  已通过: 'success',
  已完成: 'success',
  pending: 'warning',
  auditing: 'warning',
  processing: 'warning',
  partial: 'warning',
  待审: 'warning',
  进行中: 'warning',
  待处理: 'warning',
  部分完成: 'warning',
  locked: 'danger',
  rejected: 'danger',
  failed: 'danger',
  overdue: 'danger',
  错误: 'danger',
  锁定: 'danger',
  驳回: 'danger',
  失败: 'danger',
  已逾期: 'danger',
  disabled: 'info',
  inactive: 'info',
  draft: 'info',
  canceled: 'info',
  stopped: 'info',
  停用: 'info',
  未开始: 'info',
  草稿: 'info',
  已取消: 'info',
}

/** 审批 / 流程状态固定色（不因模块改色）。 */
export const STATUS_FIXED_MAP: Readonly<Record<string, StatusSemantic>> = {
  approved: 'success',
  passed: 'success',
  已通过: 'success',
  auditing: 'warning',
  pending: 'warning',
  待审: 'warning',
  rejected: 'danger',
  驳回: 'danger',
}

/** 标签形态。 */
export type StatusShape = 'capsule' | 'dot' | 'bullet' | 'icon' | 'light'

/** 标签形态集合。 */
export const STATUS_SHAPES: readonly StatusShape[] = ['capsule', 'dot', 'bullet', 'icon', 'light']

/** 状态圆点直径（组件内置图形尺寸，属尺寸白名单豁免项）。 */
export const STATUS_BULLET_SIZE = 8

/** 状态解析结果。 */
export interface StatusDescription {
  /** 命中（或兜底）的语义色。 */
  semantic: StatusSemantic
  /** 语义色令牌变量名。 */
  token: string
  /** 展示文案（未知值回退原值文本）。 */
  text: string
  /** 是否命中已知状态（含显式指定与各层映射）。 */
  known: boolean
}

/** 状态取色输入。 */
export interface StatusResolveInput {
  /** 状态值（库值）。 */
  value?: unknown
  /** 显式指定的语义色（最高优先级）。 */
  semantic?: unknown
  /** 数据源自带色（字典条目 / 枚举选项）。 */
  sourceColor?: unknown
  /** 字段级 `值 → 语义色` 映射。 */
  colorMap?: unknown
}

/**
 * 状态值归一（去首尾空格 + 小写；布尔映射 `true` / `false`）。
 *
 * @param value 原值。
 * @returns 归一后的键。
 */
export function normalizeStatusValue(value: unknown): string {
  if (typeof value === 'boolean') {
    return value ? 'success' : 'info'
  }
  if (value === null || value === undefined) {
    return ''
  }
  return String(value).trim().toLowerCase()
}

/**
 * 是否为合法语义色。
 *
 * @param value 待判定值。
 * @returns 是否合法。
 */
export function isStatusSemantic(value: unknown): value is StatusSemantic {
  return typeof value === 'string' && (STATUS_SEMANTICS as readonly string[]).includes(value)
}

/**
 * 归一字段级颜色映射（非法值剔除）。
 *
 * @param value 原始映射。
 * @returns 归一后的映射。
 */
export function normalizeStatusColorMap(value: unknown): Record<string, StatusSemantic> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  const result: Record<string, StatusSemantic> = {}
  for (const [key, semantic] of Object.entries(value as Record<string, unknown>)) {
    if (isStatusSemantic(semantic)) {
      result[normalizeStatusValue(key)] = semantic
    }
  }
  return result
}

/**
 * 解析语义色（优先级：显式指定 → 数据源自带色 → 字段级映射 → 内置映射 → 兜底 `info`）。
 *
 * @param input 取色输入。
 * @returns 语义色。
 */
export function resolveStatusSemantic(input: StatusResolveInput): StatusSemantic {
  if (isStatusSemantic(input.semantic)) {
    return input.semantic
  }
  if (isStatusSemantic(input.sourceColor)) {
    return input.sourceColor
  }
  if (typeof input.value === 'boolean') {
    return input.value ? 'success' : 'info'
  }
  const key = normalizeStatusValue(input.value)
  const colorMap = normalizeStatusColorMap(input.colorMap)
  const mapped = colorMap[key]
  if (mapped !== undefined) {
    return mapped
  }
  const fixed = STATUS_FIXED_MAP[key]
  if (fixed !== undefined) {
    return fixed
  }
  return STATUS_BUILTIN_MAP[key] ?? STATUS_FALLBACK_SEMANTIC
}

/**
 * 语义色 → 令牌变量名。
 *
 * @param semantic 语义色。
 * @returns 令牌变量名。
 */
export function statusTokenOf(semantic: StatusSemantic): string {
  return STATUS_SEMANTIC_TOKENS[semantic]
}

/**
 * 解析展示文案（给定文案优先，否则回退原值文本）。
 *
 * @param text 显式文案。
 * @param value 状态值。
 * @returns 文案。
 */
export function resolveStatusText(text: unknown, value: unknown): string {
  if (typeof text === 'string' && text !== '') {
    return text
  }
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

/**
 * 解析状态（语义色 / 令牌 / 文案 / 已知性）。
 *
 * @param value 状态值。
 * @param options 可选：显式语义色、数据源色、字段映射、显式文案。
 * @returns 状态解析结果。
 */
export function describeStatus(
  value: unknown,
  options: StatusResolveInput & { text?: unknown } = {},
): StatusDescription {
  const semantic = resolveStatusSemantic({
    value,
    semantic: options.semantic,
    sourceColor: options.sourceColor,
    colorMap: options.colorMap,
  })
  const key = normalizeStatusValue(value)
  const known =
    isStatusSemantic(options.semantic) ||
    isStatusSemantic(options.sourceColor) ||
    key === 'success' ||
    key === 'info' ||
    normalizeStatusColorMap(options.colorMap)[key] !== undefined ||
    STATUS_FIXED_MAP[key] !== undefined ||
    STATUS_BUILTIN_MAP[key] !== undefined
  return {
    semantic,
    token: statusTokenOf(semantic),
    text: resolveStatusText(options.text, value),
    known,
  }
}
