/**
 * 菜单记录页「挂接配置」草稿纯函数：按钮 / 字段明细的差异比对、校验、排序与载荷组装。
 *
 * 口径（《03_03_01 详细设计》§6.4 / §6.5）：按钮与字段为**页内内联明细**，改动只进草稿，
 * 随宿主工具栏「保存」一次提交；新增项先建后记 ID，已有项按 ID 更新，删除项按 ID 删除。
 */

import type { ButtonPayload, FieldPayload, I18nNames, MetaStatus } from '@/api/menuMeta'

/** 按钮草稿行。 */
export interface ButtonDraft {
  /** 按钮主键（新增行为 `undefined`）。 */
  id?: string
  /** 所属表单 ID。 */
  form_id: string
  /** 挂接权限码 ID。 */
  permission_id: string
  /** 按钮名。 */
  name: string
  /** 按钮形态。 */
  type: 'toolbar' | 'interface'
  /** 同表内排序。 */
  sort: number
  /** 状态。 */
  status: MetaStatus
}

/** 字段草稿行。 */
export interface FieldDraft {
  /** 字段主键（新增行为 `undefined`）。 */
  id?: string
  /** 所属表单 ID。 */
  form_id: string
  /** 字段键（表单内唯一）。 */
  field_key: string
  /** 字段类型。 */
  type: string
  /** 同表内排序。 */
  sort: number
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/** 按钮差异。 */
export interface ButtonDiff {
  /** 新增行。 */
  created: ButtonDraft[]
  /** 变更行。 */
  updated: ButtonDraft[]
  /** 删除的按钮主键。 */
  deleted: string[]
}

/** 字段差异。 */
export interface FieldDiff {
  /** 新增行。 */
  created: FieldDraft[]
  /** 变更行。 */
  updated: FieldDraft[]
  /** 删除的字段主键。 */
  deleted: string[]
}

/**
 * 按钮行比较键（忽略 `sort` 之外的展示态；`sort` 参与比较）。
 *
 * @param row 按钮草稿行。
 * @returns 比较串。
 */
function buttonSignature(row: ButtonDraft): string {
  return [row.permission_id, row.name, row.type, String(row.sort), row.status].join('|')
}

/**
 * 字段行比较键。
 *
 * @param row 字段草稿行。
 * @returns 比较串。
 */
function fieldSignature(row: FieldDraft): string {
  return [row.type, String(row.sort), row.status, JSON.stringify(sortI18n(row.i18n))].join('|')
}

/**
 * 多语言映射按键排序（保证脏态比对稳定）。
 *
 * @param i18n 多语言映射。
 * @returns 排序后的新对象。
 */
export function sortI18n(i18n: I18nNames): I18nNames {
  const result: I18nNames = {}
  for (const key of Object.keys(i18n).sort()) {
    result[key] = i18n[key] ?? ''
  }
  return result
}

/**
 * 计算按钮差异。
 *
 * @param original 载入基线。
 * @param current 当前草稿。
 * @returns 差异。
 */
export function diffButtons(original: readonly ButtonDraft[], current: readonly ButtonDraft[]): ButtonDiff {
  const originalById = new Map(original.filter((row) => row.id !== undefined).map((row) => [row.id as string, row]))
  const currentIds = new Set(current.filter((row) => row.id !== undefined).map((row) => row.id as string))
  const diff: ButtonDiff = { created: [], updated: [], deleted: [] }
  for (const row of current) {
    if (row.id === undefined) {
      diff.created.push(row)
      continue
    }
    const before = originalById.get(row.id)
    if (before !== undefined && buttonSignature(before) !== buttonSignature(row)) {
      diff.updated.push(row)
    }
  }
  for (const id of originalById.keys()) {
    if (!currentIds.has(id)) {
      diff.deleted.push(id)
    }
  }
  return diff
}

/**
 * 计算字段差异。
 *
 * @param original 载入基线。
 * @param current 当前草稿。
 * @returns 差异。
 */
export function diffFields(original: readonly FieldDraft[], current: readonly FieldDraft[]): FieldDiff {
  const originalById = new Map(original.filter((row) => row.id !== undefined).map((row) => [row.id as string, row]))
  const currentIds = new Set(current.filter((row) => row.id !== undefined).map((row) => row.id as string))
  const diff: FieldDiff = { created: [], updated: [], deleted: [] }
  for (const row of current) {
    if (row.id === undefined) {
      diff.created.push(row)
      continue
    }
    const before = originalById.get(row.id)
    if (before !== undefined && fieldSignature(before) !== fieldSignature(row)) {
      diff.updated.push(row)
    }
  }
  for (const id of originalById.keys()) {
    if (!currentIds.has(id)) {
      diff.deleted.push(id)
    }
  }
  return diff
}

/**
 * 是否空差异。
 *
 * @param diff 差异。
 * @returns 是否无变更。
 */
export function isEmptyDiff(diff: ButtonDiff | FieldDiff): boolean {
  return diff.created.length === 0 && diff.updated.length === 0 && diff.deleted.length === 0
}

/**
 * 按钮草稿校验。
 *
 * @param rows 按钮草稿行。
 * @returns 错误文案；通过返回 `undefined`。
 */
export function validateButtons(rows: readonly ButtonDraft[]): string | undefined {
  for (const row of rows) {
    if (row.name.trim() === '') {
      return '按钮名称必填'
    }
    if (row.permission_id === '') {
      return '按钮挂接权限码必填'
    }
  }
  const seen = new Set<string>()
  for (const row of rows) {
    const key = `${row.form_id}:${row.permission_id}`
    if (seen.has(key)) {
      return '同一表单内权限码不可重复'
    }
    seen.add(key)
  }
  return undefined
}

/**
 * 字段草稿校验（字段键表单内唯一 → `40205`）。
 *
 * @param rows 字段草稿行。
 * @returns 错误文案；通过返回 `undefined`。
 */
export function validateFields(rows: readonly FieldDraft[]): string | undefined {
  for (const row of rows) {
    if (row.field_key.trim() === '') {
      return '字段标识必填'
    }
    if (row.type.trim() === '') {
      return '字段类型必填'
    }
  }
  const seen = new Set<string>()
  for (const row of rows) {
    const key = `${row.form_id}:${row.field_key}`
    if (seen.has(key)) {
      return '字段标识重复（40205）'
    }
    seen.add(key)
  }
  return undefined
}

/**
 * 挂接配置指纹（脏态比对：关联表单 + 各表单按钮 / 字段草稿）。
 *
 * @param formIds 当前关联表单 ID。
 * @param buttons 按钮草稿（表单 ID → 行）。
 * @param fields 字段草稿（表单 ID → 行）。
 * @returns 稳定字符串指纹。
 */
export function linkFingerprint(
  formIds: readonly string[],
  buttons: Readonly<Record<string, readonly ButtonDraft[]>>,
  fields: Readonly<Record<string, readonly FieldDraft[]>>,
): string {
  const formPart = [...formIds].sort().join(',')
  const buttonPart = Object.keys(buttons)
    .sort()
    .map((key) =>
      (buttons[key] as ButtonDraft[])
        .map((row) => [row.id ?? 'new', buttonSignature(row)].join('|'))
        .sort()
        .join(';'),
    )
    .join('||')
  const fieldPart = Object.keys(fields)
    .sort()
    .map((key) =>
      (fields[key] as FieldDraft[])
        .map((row) => [row.id ?? 'new', row.field_key, fieldSignature(row)].join('|'))
        .sort()
        .join(';'),
    )
    .join('||')
  return `${formPart}#${buttonPart}#${fieldPart}`
}

/**
 * 下一个明细排序值。
 *
 * @param rows 同表单草稿行。
 * @returns `(最大 sort) + 10`。
 */
export function nextRowSort(rows: readonly { sort: number }[]): number {
  return rows.reduce((value, row) => Math.max(value, row.sort), 0) + 10
}

/**
 * 行内上移 / 下移（重排后按 10 / 20 / 30… 重算排序）。
 *
 * @param rows 草稿行。
 * @param index 当前下标。
 * @param delta 位移（`-1` 上移 / `1` 下移）。
 * @returns 新数组；越界时原样返回副本。
 */
export function moveDraftRow<T extends { sort: number }>(rows: readonly T[], index: number, delta: number): T[] {
  const next = rows.map((row) => ({ ...row }))
  const target = index + delta
  if (index < 0 || index >= next.length || target < 0 || target >= next.length) {
    return next
  }
  const row = next.splice(index, 1)[0] as T
  next.splice(target, 0, row)
  return next.map((item, position) => ({ ...item, sort: (position + 1) * 10 }))
}

/**
 * 按钮草稿 → 请求载荷。
 *
 * @param row 按钮草稿行。
 * @param includeForm 是否携带 `form_id`（新增携带 / 更新不携带）。
 * @returns 请求载荷。
 */
export function toButtonPayload(row: ButtonDraft, includeForm: boolean): ButtonPayload {
  const payload: ButtonPayload = {
    permission_id: row.permission_id,
    name: row.name,
    type: row.type,
    sort: row.sort,
    status: row.status,
  }
  if (includeForm) {
    payload.form_id = row.form_id
  }
  return payload
}

/**
 * 字段草稿 → 请求载荷。
 *
 * @param row 字段草稿行。
 * @param includeKeys 是否携带 `form_id` / `field_key`（新增携带 / 更新不携带）。
 * @returns 请求载荷。
 */
export function toFieldPayload(row: FieldDraft, includeKeys: boolean): FieldPayload {
  const payload: FieldPayload = {
    type: row.type,
    sort: row.sort,
    status: row.status,
    i18n: sortI18n(row.i18n),
  }
  if (includeKeys) {
    payload.form_id = row.form_id
    payload.field_key = row.field_key
  }
  return payload
}
