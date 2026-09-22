/** 样例模块领域类型与选项（首个模块样例「示例数据管理」）。
 *
 * 仅承载样例业务的值对象与选项常量；页面与服务共用，保持模块自包含（不依赖宿主）。
 */

import type { StatusSemantic } from '@bms/core'

/** 示例数据分类。 */
export type SampleCategory = 'hardware' | 'software' | 'service' | 'other'

/** 示例数据优先级。 */
export type SamplePriority = 'low' | 'normal' | 'high' | 'urgent'

/** 示例数据状态。 */
export type SampleStatus = 'draft' | 'pending' | 'active' | 'closed'

/** 示例数据记录。 */
export interface SampleRecord {
  /** 主键。 */
  id: string
  /** 编码（自动生成）。 */
  code: string
  /** 名称。 */
  name: string
  /** 分类。 */
  category: SampleCategory
  /** 优先级。 */
  priority: SamplePriority
  /** 金额。 */
  amount: number
  /** 状态。 */
  status: SampleStatus
  /** 负责人。 */
  owner: string
  /** 创建时间（ISO）。 */
  createdAt: string
  /** 更新时间（ISO）。 */
  updatedAt: string
  /** 备注。 */
  remark: string
}

/** 新建 / 编辑入参（不含自动字段）。 */
export type SampleInput = Omit<SampleRecord, 'id' | 'code' | 'createdAt' | 'updatedAt'>

/** 列表查询入参（分页 + 筛选，对齐未来统一分页口径）。 */
export interface SampleQuery {
  /** 关键词（编码 / 名称模糊）。 */
  keyword?: string
  /** 分类筛选。 */
  category?: SampleCategory
  /** 状态筛选。 */
  status?: SampleStatus
  /** 页码（从 1 起）。 */
  page: number
  /** 页长。 */
  size: number
}

/** 统一分页响应（对齐后端 `{ list, total, page, size }`）。 */
export interface SamplePage {
  /** 当前页数据。 */
  list: SampleRecord[]
  /** 总条数。 */
  total: number
  /** 页码。 */
  page: number
  /** 页长。 */
  size: number
}

/** 分类选项（值 + 文案键）。 */
export const SAMPLE_CATEGORIES: readonly { value: SampleCategory; labelKey: string }[] = [
  { value: 'hardware', labelKey: 'sample.category.hardware' },
  { value: 'software', labelKey: 'sample.category.software' },
  { value: 'service', labelKey: 'sample.category.service' },
  { value: 'other', labelKey: 'sample.category.other' },
]

/** 优先级选项（值 + 文案键）。 */
export const SAMPLE_PRIORITIES: readonly { value: SamplePriority; labelKey: string }[] = [
  { value: 'low', labelKey: 'sample.priority.low' },
  { value: 'normal', labelKey: 'sample.priority.normal' },
  { value: 'high', labelKey: 'sample.priority.high' },
  { value: 'urgent', labelKey: 'sample.priority.urgent' },
]

/** 状态选项（值 + 文案键）。 */
export const SAMPLE_STATUSES: readonly { value: SampleStatus; labelKey: string }[] = [
  { value: 'draft', labelKey: 'sample.status.draft' },
  { value: 'pending', labelKey: 'sample.status.pending' },
  { value: 'active', labelKey: 'sample.status.active' },
  { value: 'closed', labelKey: 'sample.status.closed' },
]

/** 状态 → 语义色（供 `StatusTag` 消费）。 */
export const SAMPLE_STATUS_SEMANTIC: Readonly<Record<SampleStatus, StatusSemantic>> = {
  draft: 'info',
  pending: 'warning',
  active: 'success',
  closed: 'primary',
}

/** 优先级 → 语义色（供 `SamplePriorityTag` 消费）。 */
export const SAMPLE_PRIORITY_SEMANTIC: Readonly<Record<SamplePriority, StatusSemantic>> = {
  low: 'info',
  normal: 'success',
  high: 'warning',
  urgent: 'danger',
}

/**
 * 取选项文案键。
 *
 * @param options 选项集合。
 * @param value 取值（可能为空）。
 * @returns 命中的文案键；未命中返回空串。
 */
export function labelKeyOf<T extends string>(options: readonly { value: T; labelKey: string }[], value: unknown): string {
  return options.find((item) => item.value === value)?.labelKey ?? ''
}
