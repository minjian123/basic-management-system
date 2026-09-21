/**
 * 领域纯函数：表单布局元数据契约（layout_config）。
 *
 * 设计器产出与渲染器输入**同一形状**（`resolveEffectiveLayout` / `toRenderMetadata`），
 * 三级层级解析与逐级回退、结构操作（不可变）、自建字段列名派生、校验与脏基线比对均在此集中；
 * 框架无关、不触 DOM、不请求，同输入同输出。
 */

import type { FieldPermission } from '../capabilities/field-perm'

import type { CaptchaKind, CaptchaScene } from './captcha'
import { stableStringify } from './serialize'

/** 自建字段类型白名单（对齐《概要设计 · 表单定制》「组件类型与自建字段边界」节；富文本不放开）。 */
export const EXT_FIELD_TYPES: readonly string[] = [
  'text',
  'longtext',
  'number',
  'datetime',
  'select',
  'multi_select',
  'switch',
  'file',
]
/** 需要选项集的自建字段类型（下拉单选 / 多选）。 */
export const EXT_OPTION_TYPES: readonly string[] = ['select', 'multi_select']

/** 表单定制权限码（布局 / 属性 / 自建字段维护）。 */
export const FORMDESIGN_PERM = 'formdesign:manage'
/** 渲染路径权限码（登录即可）。 */
export const FORMDESIGN_VIEW_PERM = 'formdesign:query'
/** 设计器占位文案（数据通路未就绪）。 */
export const DESIGNER_PLACEHOLDER_TEXT = '表单设计器未就绪（占位）'
/** 布局落点提示文案（拖入字段自动建分区）。 */
export const DESIGNER_EMPTY_HINT = '暂无布局分区（拖入字段将自动新建分区）'
/** 自建字段列名前缀（后端生成，前端仅预览）。 */
export const EXT_COLUMN_PREFIX = 'ext_'
/** 分区列数白名单。 */
export const SECTION_COLUMNS: readonly [1, 2, 3] = [1, 2, 3]
/** 单分区字段数建议上限（超出提示分区，不阻断）。 */
export const SECTION_FIELD_HINT = 8
/** 空布局回退的缺省列数。 */
export const DEFAULT_LAYOUT_COLUMNS = 3
/** 标签宽度缺省值（`labelPosition === 'left'` 时生效）。 */
export const DEFAULT_LABEL_WIDTH = 100
/** 标签宽度上下限。 */
export const LABEL_WIDTH_RANGE: readonly [number, number] = [0, 400]
/** 明细列宽上下限（像素）。 */
export const DETAIL_WIDTH_RANGE: readonly [number, number] = [40, 800]
/** 空布局回退的分区键（渲染与设计同源）。 */
export const DEFAULT_SECTION_KEY = 'default'
/** 自动建分区的键前缀。 */
export const SECTION_KEY_PREFIX = 'section-'

/** 设计层级。 */
export type DesignerLevel = 'platform' | 'tenant' | 'role'
/** 标签位置。 */
export type LayoutLabelPosition = 'top' | 'left'
/** 字段来源分组。 */
export type FieldGroup = 'platform' | 'tenant'
/** 自建字段 DDL 状态。 */
export type ExtDdlStatus = 'pending' | 'active' | 'failed'
/** 字段停用态（与 DDL 状态并列展示）。 */
export type FieldStatus = ExtDdlStatus | 'disabled'
/** 分区列数。 */
export type SectionColumns = 1 | 2 | 3

/** 画布选中对象。 */
export interface DesignerSelection {
  /** 对象类型。 */
  kind: 'field' | 'section'
  /** 对象键。 */
  key: string
}

/** 字段引用（分区内顺序与跨列）。 */
export interface LayoutFieldRef {
  /** 字段键。 */
  key: string
  /** 是否跨整行。 */
  colSpan?: boolean
}

/** 字段引用装载输入（兼容裸字符串与 `colspan` 写法）。 */
export type LayoutFieldRefInput = string | { key?: string; colSpan?: boolean; colspan?: boolean }

/** 分区内分组（二级组织，可选）。 */
export interface LayoutGroup {
  /** 分组键。 */
  key: string
  /** 分组标题。 */
  title: string
  /** 分组内字段引用。 */
  fields: LayoutFieldRef[]
}

/** 分组装载输入（键与标题可缺省）。 */
export interface LayoutGroupInput {
  /** 分组键。 */
  key?: string
  /** 分组标题。 */
  title?: string
  /** 分组内字段引用。 */
  fields?: readonly LayoutFieldRefInput[]
}

/** 布局分区。 */
export interface LayoutSection {
  /** 分区键。 */
  key: string
  /** 分区标题。 */
  title: string
  /** 列数（1 / 2 / 3）。 */
  columns: SectionColumns
  /** 可选分组（二级组织）。 */
  groups?: LayoutGroup[]
  /** 字段引用列表。 */
  fields: LayoutFieldRef[]
}

/** 分区装载输入（键与标题可缺省）。 */
export interface LayoutSectionInput {
  /** 分区键。 */
  key?: string
  /** 分区标题。 */
  title?: string
  /** 列数（非法值回落缺省）。 */
  columns?: number
  /** 可选分组。 */
  groups?: readonly LayoutGroupInput[]
  /** 字段引用列表。 */
  fields: readonly LayoutFieldRefInput[]
}

/** 主表结构。 */
export interface LayoutMain {
  /** 标签位置。 */
  labelPosition: LayoutLabelPosition
  /** 标签宽度（`left` 时生效）。 */
  labelWidth?: number
  /** 分区列表。 */
  sections: LayoutSection[]
}

/** 查询表单区（列表页筛选）。 */
export interface LayoutQuery {
  /** 查询字段引用。 */
  fields: string[]
}

/** 明细区列。 */
export interface LayoutDetailColumn {
  /** 列字段键。 */
  key: string
  /** 列宽（像素）。 */
  width?: number
}

/** 明细列装载输入（兼容裸字符串与对象写法）。 */
export type LayoutDetailColumnInput = string | { key?: string; width?: number }

/** 明细区（主从模块）。 */
export interface LayoutDetail {
  /** 列引用列表。 */
  columns: LayoutDetailColumn[]
}

/** 字典高级查询界面配置（可选）。 */
export interface LayoutDictAdvanced {
  /** 属性字段。 */
  fields?: string[]
  /** 操作符集合。 */
  operators?: string[]
  /** 默认方案。 */
  scheme?: string
  /** 结果列。 */
  columns?: string[]
}

/** 布局装载输入（后端 JSON 可省略字段、可写裸字符串引用）。 */
export interface FormLayoutInput {
  /** 主表。 */
  main?: {
    /** 标签位置。 */
    labelPosition?: LayoutLabelPosition
    /** 标签宽度。 */
    labelWidth?: number
    /** 分区列表。 */
    sections?: readonly LayoutSectionInput[]
  }
  /** 查询表单区。 */
  query?: { fields?: readonly LayoutFieldRefInput[] }
  /** 明细区。 */
  detail?: { columns?: readonly LayoutDetailColumnInput[] }
  /** 字典高级查询界面配置。 */
  dictAdvanced?: {
    /** 属性字段。 */
    fields?: readonly LayoutFieldRefInput[]
    /** 操作符集合。 */
    operators?: readonly (string | undefined)[]
    /** 默认方案。 */
    scheme?: string
    /** 结果列。 */
    columns?: readonly LayoutFieldRefInput[]
  }
}

/** 布局模型（`sys_form_layout.layout_config` 的结构部分；运行态确定值）。 */
export interface FormLayout {
  /** 主表。 */
  main: LayoutMain
  /** 查询表单区。 */
  query?: LayoutQuery
  /** 明细区。 */
  detail?: LayoutDetail
  /** 字典高级查询界面配置。 */
  dictAdvanced?: LayoutDictAdvanced
}

/** 字段属性规则描述（声明式，编译归 `domain/form-render`）。 */
export interface FieldRule {
  /** 规则种类（必填 / 长度 / 数值范围 / 正则 / 选项集）。 */
  kind: 'required' | 'length' | 'range' | 'pattern' | 'options'
  /** 长度或数值下限。 */
  min?: number
  /** 长度或数值上限。 */
  max?: number
  /** 正则（`pattern` 规则）。 */
  pattern?: string
  /** 自定义错误文案（缺省按规则种类取默认文案）。 */
  message?: string
}

/**
 * 字段渲染属性（后端可省略；省略项按缺省，运行态由 `domain/form-render` 归一）。
 *
 * 由 `08-6-2` 渲染器按需**向后兼容新增**（既有字段语义不变），随 `layout-effective` 一次下发。
 */
export interface FieldRenderAttrs {
  /** 是否必填（权限 `required` 可覆盖）。 */
  required?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 默认值（记录未提供该字段值时使用）。 */
  defaultValue?: unknown
  /** 校验规则（声明式）。 */
  rules?: readonly FieldRule[]
  /** 选项集（下拉 / 单选 / 复选 / 穿梭等）。 */
  options?: readonly ExtFieldOption[]
  /** 字典类型（选项集引用字典；与 `select` / `multi_select` 或 `dict` / `dict_multi` 字段类型协作）。 */
  dictType?: string
  /** 上传接受类型（扩展名 / MIME，逗号分隔；`file-upload` / `image-upload` 字段类型协作）。 */
  uploadAccept?: string
  /** 上传单文件大小上限（字节）。 */
  uploadMaxSize?: number
  /** 上传数量上限（0 / 缺省表示不限）。 */
  uploadLimit?: number
  /** 上传是否多选（缺省多选）。 */
  uploadMultiple?: boolean
  /** 验证码形态（`captcha` 字段类型协作；缺省图形）。 */
  captchaKind?: CaptchaKind
  /** 验证码使用场景（`captcha` 字段类型协作；缺省登录）。 */
  captchaScene?: CaptchaScene
  /** 只读（编辑态亦只读）。 */
  readonly?: boolean
  /** 隐藏（布局引用但默认不渲染）。 */
  hidden?: boolean
}

/** 字段清单项（平台字段 + 租户自建字段合并下发）。 */
export interface FormField extends FieldRenderAttrs {
  /** 字段键。 */
  key: string
  /** 字段名（当前 locale）。 */
  label: string
  /** 字段类型。 */
  type: string
  /** 来源分组。 */
  group: FieldGroup
  /** 是否不可拖入（停用 / 建列失败）。 */
  disabled?: boolean
  /** 状态标记。 */
  status?: FieldStatus
}

/** 三级层级布局（同表单下各层级各一份，可缺失）。 */
export interface FormLayoutLevels {
  /** 平台默认。 */
  platform?: FormLayout
  /** 租户覆盖。 */
  tenant?: FormLayout
  /** 角色视图。 */
  role?: FormLayout
}

/** 生效布局（渲染输入；设计器与渲染器共用）。 */
export interface LayoutEffective {
  /** 生效布局（命中层级或空布局回退默认栅格）。 */
  layout: FormLayout
  /** 合并字段清单。 */
  fields: FormField[]
  /** 当前层级。 */
  level: DesignerLevel
  /** 实际来源层级（`empty` 表示空布局回退）。 */
  source: DesignerLevel | 'empty'
  /** 是否只读。 */
  readonly: boolean
  /** 是否走了空布局回退。 */
  fallback: boolean
  /** 当前用户字段权限标记（键为字段键；缺省项按全开，由 `08-6-2` 渲染器叠加）。 */
  permissions?: Readonly<Record<string, FieldPermission>>
}

/** 恢复默认目标。 */
export interface LayoutRestoreTarget {
  /** 目标层级（删除该层级配置）。 */
  level: DesignerLevel
  /** 是否删除配置。 */
  remove: boolean
  /** 回退到哪一级（`empty` 表示空布局回退）。 */
  fallbackTo: DesignerLevel | 'empty'
}

/** 布局校验问题种类。 */
export type LayoutIssueKind = 'unknown-field' | 'disabled-field' | 'duplicate-field' | 'empty-section' | 'columns'

/** 布局校验问题。 */
export interface LayoutValidationIssue {
  /** 问题种类。 */
  kind: LayoutIssueKind
  /** 涉事分区键。 */
  sectionKey?: string
  /** 涉事字段键。 */
  fieldKey?: string
  /** 说明。 */
  message: string
}

/** 布局校验结果。 */
export interface LayoutValidationResult {
  /** 是否通过（无问题）。 */
  valid: boolean
  /** 问题清单。 */
  errors: LayoutValidationIssue[]
  /** 汇总文案。 */
  message: string
}

/** 自建字段选项项。 */
export interface ExtFieldOption {
  /** 选项值。 */
  value: string
  /** 选项文本。 */
  label: string
}

/** 自建字段草稿（装载输入，可省略项在归一后确定）。 */
export interface ExtFieldDraft {
  /** 名称（中文）。 */
  name: string
  /** 名称（英文，i18n）。 */
  nameEn?: string
  /** 类型。 */
  type: string
  /** 选项集（下拉类必填）。 */
  options?: readonly ExtFieldOption[]
}

/** 自建字段校验结果（含派生列名）。 */
export interface ExtFieldCheck {
  /** 是否通过。 */
  valid: boolean
  /** 派生列名（`ext_` 前缀）。 */
  columnName: string
  /** 失败原因（通过时为空串）。 */
  message: string
}

/** 空布局。 */
export function emptyLayout(): FormLayout {
  return { main: { labelPosition: 'top', sections: [] } }
}

/**
 * 空布局回退：按字段清单顺序生成默认栅格。
 *
 * @param fields 合并字段清单。
 * @param columns 列数（缺省 3）。
 * @returns 默认栅格布局。
 */
export function defaultLayout(
  fields: readonly FormField[],
  columns: SectionColumns = DEFAULT_LAYOUT_COLUMNS,
): FormLayout {
  const usable = fields.filter(
    (field) => field.disabled !== true && (field.status === undefined || field.status === 'active'),
  )
  return {
    main: {
      labelPosition: 'top',
      sections: [
        {
          key: DEFAULT_SECTION_KEY,
          title: '',
          columns: normalizeColumns(columns),
          fields: usable.map((field) => ({ key: field.key })),
        },
      ],
    },
  }
}

/**
 * 是否为空布局（无有效分区或所有分区均无字段引用）。
 *
 * @param layout 布局。
 */
export function isLayoutEmpty(layout: FormLayout | undefined): boolean {
  if (layout === undefined || layout.main === undefined) {
    return true
  }
  return layout.main.sections.every((section) => (section.fields ?? []).length === 0)
}

/** 取字段引用键（兼容字符串与对象两种写法）。 */
function refKey(input: unknown): string | undefined {
  if (typeof input === 'string') {
    return input.trim() === '' ? undefined : input
  }
  if (input !== null && typeof input === 'object') {
    const key = (input as { key?: unknown }).key
    if (typeof key === 'string' && key.trim() !== '') {
      return key
    }
  }
  return undefined
}

/** 是否跨列（兼容 `colSpan` / `colspan` 两种写法）。 */
function refColSpan(input: unknown): boolean {
  if (input === null || typeof input !== 'object') {
    return false
  }
  const record = input as { colSpan?: unknown; colspan?: unknown }
  return record.colSpan === true || record.colspan === true
}

/**
 * 归一单个字段引用（空键返回 `undefined`）。
 *
 * @param ref 原始引用。
 */
export function normalizeFieldRef(
  ref: { key?: string; colSpan?: boolean } | string | undefined,
): LayoutFieldRef | undefined {
  const key = refKey(ref)
  if (key === undefined) {
    return undefined
  }
  return refColSpan(ref) ? { key, colSpan: true } : { key }
}

/**
 * 归一字段引用列表（剔空键、去重保序、并合跨列标记）。
 *
 * @param refs 原始引用列表。
 */
export function normalizeFieldRefs(refs: readonly unknown[] | undefined): LayoutFieldRef[] {
  const result: LayoutFieldRef[] = []
  const seen = new Set<string>()
  for (const item of refs ?? []) {
    const ref = normalizeFieldRef(item as { key?: string; colSpan?: boolean } | string)
    if (ref === undefined) {
      continue
    }
    if (seen.has(ref.key)) {
      const existing = result.find((entry) => entry.key === ref.key)
      if (existing !== undefined && ref.colSpan === true) {
        existing.colSpan = true
      }
      continue
    }
    seen.add(ref.key)
    result.push(ref)
  }
  return result
}

/**
 * 归一列数（仅 1 / 2 / 3 合法，其余回落缺省 3）。
 *
 * @param value 原始值。
 */
export function normalizeColumns(value: unknown): SectionColumns {
  const parsed = typeof value === 'number' ? value : Number(value)
  return parsed === 1 || parsed === 2 || parsed === 3 ? parsed : DEFAULT_LAYOUT_COLUMNS
}

/** 夹取整数到区间。 */
function clampInt(value: unknown, range: readonly [number, number], fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) {
    return fallback
  }
  const rounded = Math.trunc(parsed)
  return Math.min(Math.max(rounded, range[0]), range[1])
}

/**
 * 归一布局（缺省项补确定值，失败引用不抛错；装载输入兼容裸字符串引用）。
 *
 * @param input 原始布局。
 */
export function normalizeLayout(input: FormLayout | FormLayoutInput | undefined): FormLayout {
  if (input === undefined || input === null || input.main === undefined) {
    return emptyLayout()
  }
  const main = input.main
  const sections: LayoutSection[] = (main.sections ?? []).map((section, index) => {
    const groups = Array.isArray(section.groups)
      ? section.groups.map((group, groupIndex) => ({
          key:
            typeof group?.key === 'string' && group.key !== ''
              ? group.key
              : `${SECTION_KEY_PREFIX}${index + 1}-g${groupIndex + 1}`,
          title: typeof group?.title === 'string' ? group.title : '',
          fields: normalizeFieldRefs(group?.fields),
        }))
      : undefined
    const normalized: LayoutSection = {
      key: typeof section?.key === 'string' && section.key !== '' ? section.key : `${SECTION_KEY_PREFIX}${index + 1}`,
      title: typeof section?.title === 'string' ? section.title : '',
      columns: normalizeColumns(section?.columns),
      fields: normalizeFieldRefs(section?.fields),
    }
    if (groups !== undefined && groups.length > 0) {
      normalized.groups = groups
    }
    return normalized
  })

  const result: FormLayout = {
    main: {
      labelPosition: main.labelPosition === 'left' ? 'left' : 'top',
      sections,
    },
  }
  if (main.labelWidth !== undefined) {
    result.main.labelWidth = clampInt(main.labelWidth, LABEL_WIDTH_RANGE, DEFAULT_LABEL_WIDTH)
  }
  if (input.query !== undefined && Array.isArray(input.query.fields)) {
    result.query = { fields: normalizeFieldRefs(input.query.fields).map((ref) => ref.key) }
  }
  if (input.detail !== undefined && Array.isArray(input.detail.columns)) {
    result.detail = { columns: normalizeDetailColumns(input.detail.columns) }
  }
  if (input.dictAdvanced !== undefined && input.dictAdvanced !== null) {
    const advanced: LayoutDictAdvanced = {}
    const fields = normalizeFieldRefs(input.dictAdvanced.fields ?? []).map((ref) => ref.key)
    if (fields.length > 0) {
      advanced.fields = fields
    }
    if (Array.isArray(input.dictAdvanced.operators) && input.dictAdvanced.operators.length > 0) {
      advanced.operators = input.dictAdvanced.operators.filter(
        (item): item is string => typeof item === 'string' && item !== '',
      )
    }
    if (typeof input.dictAdvanced.scheme === 'string' && input.dictAdvanced.scheme !== '') {
      advanced.scheme = input.dictAdvanced.scheme
    }
    const columns = normalizeFieldRefs(input.dictAdvanced.columns ?? []).map((ref) => ref.key)
    if (columns.length > 0) {
      advanced.columns = columns
    }
    if (Object.keys(advanced).length > 0) {
      result.dictAdvanced = advanced
    }
  }
  return result
}

/** 归一明细列（兼容字符串与对象两种写法，去重保序，宽度夹取）。 */
export function normalizeDetailColumns(columns: readonly LayoutDetailColumnInput[]): LayoutDetailColumn[] {
  const result: LayoutDetailColumn[] = []
  const seen = new Set<string>()
  for (const item of columns) {
    const key = refKey(item)
    if (key === undefined || seen.has(key)) {
      continue
    }
    seen.add(key)
    const width = item !== null && typeof item === 'object' ? (item as { width?: unknown }).width : undefined
    if (width !== undefined) {
      result.push({ key, width: clampInt(width, DETAIL_WIDTH_RANGE, 0) })
    } else {
      result.push({ key })
    }
  }
  return result
}

/**
 * 收集布局引用的字段键（主表 + 查询区 + 明细区 + 字典高级查询，去重保序）。
 *
 * @param layout 布局。
 */
export function collectFieldKeys(layout: FormLayout | undefined): string[] {
  if (layout === undefined) {
    return []
  }
  const normalized = normalizeLayout(layout)
  const keys: string[] = []
  const push = (key: string): void => {
    if (!keys.includes(key)) {
      keys.push(key)
    }
  }
  for (const section of normalized.main.sections) {
    for (const field of section.fields) {
      push(field.key)
    }
    for (const group of section.groups ?? []) {
      for (const field of group.fields) {
        push(field.key)
      }
    }
  }
  for (const key of normalized.query?.fields ?? []) {
    push(key)
  }
  for (const column of normalized.detail?.columns ?? []) {
    push(column.key)
  }
  for (const key of normalized.dictAdvanced?.fields ?? []) {
    push(key)
  }
  for (const key of normalized.dictAdvanced?.columns ?? []) {
    push(key)
  }
  return keys
}

/**
 * 统计主表字段引用数（分区内，含分组）。
 *
 * @param layout 布局。
 */
export function countLayoutFields(layout: FormLayout | undefined): number {
  if (layout === undefined) {
    return 0
  }
  return layout.main.sections.reduce((sum, section) => {
    const groups = section.groups ?? []
    return sum + section.fields.length + groups.reduce((count, group) => count + group.fields.length, 0)
  }, 0)
}

/**
 * 查找分区。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 */
export function findSection(layout: FormLayout, sectionKey: string): LayoutSection | undefined {
  return layout.main.sections.find((section) => section.key === sectionKey)
}

/**
 * 是否已在主表引用该字段。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function hasField(layout: FormLayout, fieldKey: string): boolean {
  return locateField(layout, fieldKey) !== undefined
}

/**
 * 定位字段（主表分区内，含分组）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function locateField(layout: FormLayout, fieldKey: string): { sectionKey: string; index: number } | undefined {
  for (const section of layout.main.sections) {
    const index = section.fields.findIndex((field) => field.key === fieldKey)
    if (index >= 0) {
      return { sectionKey: section.key, index }
    }
  }
  return undefined
}

/** 深拷贝布局（结构操作不可变的前提）。 */
function cloneLayout(layout: FormLayout): FormLayout {
  return normalizeLayout(JSON.parse(JSON.stringify(layout)) as FormLayout)
}

/**
 * 生成不冲突的新分区键。
 *
 * @param layout 布局。
 */
export function newSectionKey(layout: FormLayout): string {
  const used = new Set(layout.main.sections.map((section) => section.key))
  let index = layout.main.sections.length + 1
  while (used.has(`${SECTION_KEY_PREFIX}${index}`)) {
    index += 1
  }
  return `${SECTION_KEY_PREFIX}${index}`
}

/**
 * 插入字段（幂等：已存在则不重复插入；目标分区缺失时自动建分区）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 * @param sectionKey 目标分区键（缺省首个分区）。
 * @param index 目标索引（缺省末尾）。
 */
export function insertField(layout: FormLayout, fieldKey: string, sectionKey?: string, index?: number): FormLayout {
  if (fieldKey === '') {
    return layout
  }
  if (hasField(layout, fieldKey)) {
    return layout
  }
  const next = cloneLayout(layout)
  let target = sectionKey === undefined ? next.main.sections[0] : findSection(next, sectionKey)
  if (target === undefined) {
    target = { key: sectionKey ?? newSectionKey(next), title: '', columns: DEFAULT_LAYOUT_COLUMNS, fields: [] }
    next.main.sections.push(target)
  }
  const at = index === undefined ? target.fields.length : Math.min(Math.max(Math.trunc(index), 0), target.fields.length)
  target.fields.splice(at, 0, { key: fieldKey })
  return next
}

/**
 * 移动字段（跨分区与分区内排序同一路径：先移出再插入）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 * @param sectionKey 目标分区键。
 * @param index 目标索引（按移出后列表计算）。
 */
export function moveField(layout: FormLayout, fieldKey: string, sectionKey: string, index?: number): FormLayout {
  const located = locateField(layout, fieldKey)
  if (located === undefined) {
    return layout
  }
  const next = cloneLayout(layout)
  for (const section of next.main.sections) {
    section.fields = section.fields.filter((field) => field.key !== fieldKey)
    for (const group of section.groups ?? []) {
      group.fields = group.fields.filter((field) => field.key !== fieldKey)
    }
  }
  let target = findSection(next, sectionKey)
  if (target === undefined) {
    target = { key: sectionKey, title: '', columns: DEFAULT_LAYOUT_COLUMNS, fields: [] }
    next.main.sections.push(target)
  }
  const at = index === undefined ? target.fields.length : Math.min(Math.max(Math.trunc(index), 0), target.fields.length)
  target.fields.splice(at, 0, { key: fieldKey })
  return next
}

/**
 * 移除字段引用（字段定义不受影响，回字段调板）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function removeField(layout: FormLayout, fieldKey: string): FormLayout {
  if (!hasField(layout, fieldKey)) {
    return layout
  }
  const next = cloneLayout(layout)
  for (const section of next.main.sections) {
    section.fields = section.fields.filter((field) => field.key !== fieldKey)
    for (const group of section.groups ?? []) {
      group.fields = group.fields.filter((field) => field.key !== fieldKey)
    }
  }
  return next
}

/**
 * 翻转字段跨列。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function toggleColSpan(layout: FormLayout, fieldKey: string): FormLayout {
  if (!hasField(layout, fieldKey)) {
    return layout
  }
  const next = cloneLayout(layout)
  for (const section of next.main.sections) {
    for (const field of section.fields) {
      if (field.key === fieldKey) {
        if (field.colSpan === true) {
          delete field.colSpan
        } else {
          field.colSpan = true
        }
      }
    }
  }
  return next
}

/**
 * 设置分区列数（分区不存在时原样返回）。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 * @param columns 列数。
 */
export function setSectionColumns(layout: FormLayout, sectionKey: string, columns: unknown): FormLayout {
  const next = cloneLayout(layout)
  const target = findSection(next, sectionKey)
  if (target === undefined) {
    return layout
  }
  target.columns = normalizeColumns(columns)
  return next
}

/**
 * 重命名分区。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 * @param title 标题。
 */
export function renameSection(layout: FormLayout, sectionKey: string, title: string): FormLayout {
  const next = cloneLayout(layout)
  const target = findSection(next, sectionKey)
  if (target === undefined) {
    return layout
  }
  target.title = title
  return next
}

/**
 * 新增分区（返回新分区键；无新键返回空串）。
 *
 * @param layout 布局。
 * @param sectionKey 指定分区键（缺省自动生成）。
 * @param title 标题。
 * @param columns 列数。
 */
export function addSection(
  layout: FormLayout,
  sectionKey?: string,
  title = '',
  columns: unknown = DEFAULT_LAYOUT_COLUMNS,
): { layout: FormLayout; key: string } {
  const next = cloneLayout(layout)
  const key = sectionKey === undefined || sectionKey === '' ? newSectionKey(next) : sectionKey
  if (findSection(next, key) !== undefined) {
    return { layout, key: '' }
  }
  next.main.sections.push({ key, title, columns: normalizeColumns(columns), fields: [] })
  return { layout: next, key }
}

/**
 * 删除分区（连同其字段引用；字段定义不受影响）。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 */
export function removeSection(layout: FormLayout, sectionKey: string): FormLayout {
  if (findSection(layout, sectionKey) === undefined) {
    return layout
  }
  const next = cloneLayout(layout)
  next.main.sections = next.main.sections.filter((section) => section.key !== sectionKey)
  return next
}

/**
 * 设置标签位置。
 *
 * @param layout 布局。
 * @param position 标签位置。
 */
export function setLabelPosition(layout: FormLayout, position: LayoutLabelPosition): FormLayout {
  const next = cloneLayout(layout)
  next.main.labelPosition = position === 'left' ? 'left' : 'top'
  return next
}

/**
 * 设置标签宽度（夹取到 0 ~ 400 整数）。
 *
 * @param layout 布局。
 * @param width 宽度。
 */
export function setLabelWidth(layout: FormLayout, width: unknown): FormLayout {
  const next = cloneLayout(layout)
  next.main.labelWidth = clampInt(width, LABEL_WIDTH_RANGE, DEFAULT_LABEL_WIDTH)
  return next
}

/**
 * 设置查询区字段（字符串化 + 去重保序；空列表移除查询区配置）。
 *
 * @param layout 布局。
 * @param keys 字段键列表。
 */
export function setQueryFields(layout: FormLayout, keys: readonly (string | number)[]): FormLayout {
  const next = cloneLayout(layout)
  const fields = normalizeFieldRefs(keys).map((ref) => ref.key)
  if (fields.length === 0) {
    delete next.query
  } else {
    next.query = { fields }
  }
  return next
}

/**
 * 设置明细列（归一为 `{ key, width? }`，宽度夹取；空列表移除明细区配置）。
 *
 * @param layout 布局。
 * @param columns 列列表。
 */
export function setDetailColumns(layout: FormLayout, columns: readonly LayoutDetailColumnInput[]): FormLayout {
  const next = cloneLayout(layout)
  const normalized = normalizeDetailColumns(columns)
  if (normalized.length === 0) {
    delete next.detail
  } else {
    next.detail = { columns: normalized }
  }
  return next
}

/**
 * 归一画布选中项（缺省返回 `null`）。
 *
 * @param input 选中项。
 */
export function normalizeSelection(input: DesignerSelection | null | undefined): DesignerSelection | null {
  if (input === null || input === undefined) {
    return null
  }
  if (input.key === '' || (input.kind !== 'field' && input.kind !== 'section')) {
    return null
  }
  return { kind: input.kind, key: input.key }
}

/**
 * 解析层级只读（平台默认层级恒只读；其余层级要求维护权限）。
 *
 * @param level 层级。
 * @param hasManage 是否持维护权限。
 * @param forced 外部强制只读。
 */
export function resolveLevelReadOnly(level: DesignerLevel, hasManage: boolean, forced = false): boolean {
  if (forced) {
    return true
  }
  if (level === 'platform') {
    return true
  }
  return !hasManage
}

/**
 * 解析恢复默认目标（逐级回退：角色 → 租户 → 平台 → 空布局）。
 *
 * @param level 当前层级。
 */
export function resolveRestoreTarget(level: DesignerLevel): LayoutRestoreTarget {
  if (level === 'role') {
    return { level: 'role', remove: true, fallbackTo: 'tenant' }
  }
  if (level === 'tenant') {
    return { level: 'tenant', remove: true, fallbackTo: 'platform' }
  }
  return { level: 'platform', remove: true, fallbackTo: 'empty' }
}

/**
 * 按层级解析布局（角色视图 → 租户覆盖 → 平台默认；皆无返回 `undefined`）。
 *
 * @param levels 三级层级布局。
 * @param level 当前层级。
 */
export function resolveLayoutForLevel(
  levels: FormLayoutLevels | undefined,
  level: DesignerLevel,
): { layout: FormLayout | undefined; source: DesignerLevel | 'empty' } {
  if (levels === undefined) {
    return { layout: undefined, source: 'empty' }
  }
  const order: DesignerLevel[] =
    level === 'role' ? ['role', 'tenant', 'platform'] : level === 'tenant' ? ['tenant', 'platform'] : ['platform']
  for (const candidate of order) {
    const layout = levels[candidate]
    if (layout !== undefined && !isLayoutEmpty(layout)) {
      return { layout: normalizeLayout(layout), source: candidate }
    }
  }
  return { layout: undefined, source: 'empty' }
}

/**
 * 解析生效布局（含空布局回退与只读判定；渲染输入与设计器共用）。
 *
 * @param input 输入。
 */
export function resolveEffectiveLayout(input: {
  levels?: FormLayoutLevels
  level: DesignerLevel
  fields?: readonly FormField[]
  hasManage?: boolean
  readOnly?: boolean
  permissions?: Readonly<Record<string, FieldPermission>>
}): LayoutEffective {
  const fields = [...(input.fields ?? [])]
  const resolved = resolveLayoutForLevel(input.levels, input.level)
  const fallback = resolved.layout === undefined
  const layout = fallback ? defaultLayout(fields) : (resolved.layout as FormLayout)
  const effective: LayoutEffective = {
    layout,
    fields,
    level: input.level,
    source: resolved.source,
    readonly: resolveLevelReadOnly(input.level, input.hasManage ?? true, input.readOnly ?? false),
    fallback,
  }
  if (input.permissions !== undefined) {
    effective.permissions = input.permissions
  }
  return effective
}

/**
 * 转为渲染输入（**与设计器产出同一形状**，不重新解析、不裁剪字段）。
 *
 * @param effective 生效布局。
 */
export function toRenderMetadata(effective: LayoutEffective): LayoutEffective {
  const metadata: LayoutEffective = {
    layout: normalizeLayout(effective.layout),
    fields: [...effective.fields],
    level: effective.level,
    source: effective.source,
    readonly: effective.readonly,
    fallback: effective.fallback,
  }
  if (effective.permissions !== undefined) {
    metadata.permissions = effective.permissions
  }
  return metadata
}

/**
 * 找出布局引用的失效字段（字段清单中不存在）。
 *
 * @param layout 布局。
 * @param fields 字段清单。
 */
export function findUnknownFields(layout: FormLayout, fields: readonly FormField[]): string[] {
  const known = new Set(fields.map((field) => field.key))
  return collectFieldKeys(layout).filter((key) => !known.has(key))
}

/**
 * 找出布局引用的停用 / 建列失败字段。
 *
 * @param layout 布局。
 * @param fields 字段清单。
 */
export function findDisabledFields(layout: FormLayout, fields: readonly FormField[]): string[] {
  const disabled = new Set(
    fields
      .filter((field) => field.disabled === true || (field.status !== undefined && field.status !== 'active'))
      .map((field) => field.key),
  )
  return collectFieldKeys(layout).filter((key) => disabled.has(key))
}

/**
 * 找出被多个分区重复引用的字段。
 *
 * @param layout 布局。
 */
export function findDuplicateFields(layout: FormLayout): string[] {
  const seen = new Set<string>()
  const duplicated = new Set<string>()
  for (const section of layout.main.sections) {
    for (const field of section.fields) {
      if (seen.has(field.key)) {
        duplicated.add(field.key)
      }
      seen.add(field.key)
    }
  }
  return [...duplicated]
}

/**
 * 校验布局（失效 / 停用 / 重复 / 空分区 / 列数非法）。
 *
 * @param layout 布局。
 * @param fields 字段清单。
 */
export function validateLayout(layout: FormLayout, fields: readonly FormField[]): LayoutValidationResult {
  const normalized = normalizeLayout(layout)
  const errors: LayoutValidationIssue[] = []
  for (const key of findUnknownFields(normalized, fields)) {
    errors.push({ kind: 'unknown-field', fieldKey: key, message: `字段引用失效：${key}` })
  }
  for (const key of findDisabledFields(normalized, fields)) {
    errors.push({ kind: 'disabled-field', fieldKey: key, message: `字段已停用或建列失败：${key}` })
  }
  for (const key of findDuplicateFields(normalized)) {
    errors.push({ kind: 'duplicate-field', fieldKey: key, message: `字段被重复引用：${key}` })
  }
  for (const section of normalized.main.sections) {
    if (section.fields.length === 0) {
      errors.push({
        kind: 'empty-section',
        sectionKey: section.key,
        message: `分区无字段：${section.title || section.key}`,
      })
    }
  }
  return {
    valid: errors.length === 0,
    errors,
    message: errors.length === 0 ? '' : errors.map((issue) => issue.message).join('；'),
  }
}

/**
 * 布局逐字比对（键序无关）。
 *
 * @param a 布局甲。
 * @param b 布局乙。
 */
export function layoutEqual(a: FormLayout | undefined, b: FormLayout | undefined): boolean {
  if (a === undefined || b === undefined) {
    return a === b
  }
  return stableStringify(normalizeLayout(a)) === stableStringify(normalizeLayout(b))
}

/**
 * 是否脏（当前布局与基线比对；基线缺失视为不脏）。
 *
 * @param current 当前布局。
 * @param baseline 基线布局。
 */
export function isLayoutDirty(current: FormLayout | undefined, baseline: FormLayout | undefined): boolean {
  if (baseline === undefined) {
    return false
  }
  return !layoutEqual(current, baseline)
}

/**
 * 派生自建字段物理列名（`ext_{fieldKey 蛇形}`）。
 *
 * @param fieldKey 字段键。
 */
export function extColumnName(fieldKey: string): string {
  const snake = fieldKey
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s-.]+/g, '_')
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, '')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
  return `${EXT_COLUMN_PREFIX}${snake}`
}

/**
 * 自建字段是否需要选项集（下拉单选 / 多选）。
 *
 * @param type 类型。
 */
export function extFieldNeedsOptions(type: string): boolean {
  return EXT_OPTION_TYPES.includes(type)
}

/**
 * 校验自建字段草稿（名称 / 类型 / 唯一性 / 选项集）。
 *
 * @param draft 草稿。
 * @param existingKeys 既有字段键（平台 + 自建）。
 */
export function checkExtField(draft: ExtFieldDraft, existingKeys: readonly string[]): ExtFieldCheck {
  const columnName = extColumnName(draft.name)
  if (draft.name.trim() === '') {
    return { valid: false, columnName, message: '字段名称不能为空' }
  }
  if (!EXT_FIELD_TYPES.includes(draft.type)) {
    return { valid: false, columnName, message: `字段类型不在白名单：${draft.type}` }
  }
  if (existingKeys.includes(draft.name)) {
    return { valid: false, columnName, message: `字段名称已存在：${draft.name}` }
  }
  if (extFieldNeedsOptions(draft.type) && (draft.options ?? []).length === 0) {
    return { valid: false, columnName, message: '下拉单选 / 多选字段必须配置选项集' }
  }
  return { valid: true, columnName, message: '' }
}

/**
 * 解析 DDL 状态文案。
 *
 * @param status 状态。
 */
export function resolveExtDdlStatus(status: ExtDdlStatus | undefined): '待建列' | '已生效' | '建列失败' {
  if (status === 'active') {
    return '已生效'
  }
  if (status === 'failed') {
    return '建列失败'
  }
  return '待建列'
}

/**
 * 字段是否可拖入布局（未注册类型 / 停用 / 建列失败不可拖入）。
 *
 * @param field 字段清单项。
 * @param registeredTypes 已注册类型（空数组视为不限类型）。
 */
export function canDragField(field: FormField, registeredTypes: readonly string[]): boolean {
  if (field.disabled === true) {
    return false
  }
  if (field.status !== undefined && field.status !== 'active') {
    return false
  }
  if (registeredTypes.length === 0) {
    return true
  }
  return registeredTypes.includes(field.type)
}
