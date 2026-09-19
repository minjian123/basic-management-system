/**
 * 表单渲染器能力基类：渲染编排（三态 / 字段权限叠加 / 校验与定位 / 明细区 / 提交装配）。
 *
 * 组合表单元数据（`BaseFormMeta`）、字段权限（`BaseFieldPerm`）、权限上下文（`BaseAccess`）、
 * 提示通知（`BaseNotice`）与校验能力（`BaseValidatable`）；处理函数由宿主注入，
 * **未注入即占位**（不发请求、返回 `undefined`）；渲染语义全部经领域纯函数 `domain/form-render`。
 */

import { BaseComponent } from '../base/BaseComponent'
import {
  FORM_RENDER_PERM,
  buildRenderPlan,
  buildSubmitPayload,
  compileFieldRules,
  isSubmitAllowed,
  normalizeRenderMetadata,
  normalizeRenderMode,
  type DetailDataSet,
  type DetailRenderError,
  type DetailValidationResult,
  type FieldRenderOverride,
  type FormRenderError,
  type FormRenderMode,
  type FormValidationResult,
  type RenderDetailColumn,
  type RenderFieldPlan,
  type RenderMetadataInput,
  type RenderPlan,
  type SubmitPayload,
} from '../domain/form-render'

import { BaseAccess } from './access'
import { BaseFieldPerm } from './field-perm'
import { BaseFormMeta } from './form-meta'
import { BaseNotice } from './notice'
import { BaseValidatable } from './validatable'

import type { FieldPermission } from './field-perm'
import type { FormField, LayoutEffective } from '../domain/form-layout'

/** 渲染阶段。 */
export type RendererPhase = 'idle' | 'loading' | 'submitting' | 'done' | 'failed'

/** 详情快照（编辑 / 查看态取数）。 */
export interface RecordSnapshot {
  /** 主表数据。 */
  data?: Record<string, unknown>
  /** 明细数据。 */
  details?: DetailDataSet
  /** 记录版本（乐观锁）。 */
  recordVersion?: number
}

/** 提交结果。 */
export interface SubmitResult {
  /** 记录版本。 */
  recordVersion?: number
  /** 后端回写数据（可选）。 */
  data?: Record<string, unknown>
}

/** 注入的处理函数集（未注入项按占位：不请求、恒定返回 `undefined`）。 */
export interface FormRendererJobs {
  /** 取布局元数据（`layout-effective`）。 */
  loadLayout?: (input: {
    formCode: string
    mode: FormRenderMode
    recordId?: string | number
  }) => Promise<RenderMetadataInput | LayoutEffective | undefined>
  /** 取详情（编辑 / 查看态）。 */
  loadRecord?: (input: { formCode: string; recordId: string | number }) => Promise<RecordSnapshot | undefined>
  /** 主从单事务提交。 */
  submit?: (input: SubmitPayload) => Promise<SubmitResult | undefined>
}

/** 表单渲染器能力基类（抽象）。 */
export abstract class BaseFormRenderer extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'form-renderer'
  /** 依赖能力键（表单元数据 / 字段权限 / 权限 / 提示 / 校验）。 */
  override readonly depends = ['form-meta', 'field-perm', 'access', 'notice', 'validatable']
  /** 表单标识。 */
  formCode = ''
  /** 三态。 */
  mode: FormRenderMode = 'create'
  /** 记录主键。 */
  recordId: string | number | undefined
  /** 强制只读（覆盖三态）。 */
  forceReadOnly = false
  /** 数据通路是否就绪。 */
  ready = false
  /** 已发起的后端请求计数（占位期恒 0）。 */
  requestCount = 0
  /** 生效布局元数据。 */
  meta: LayoutEffective = normalizeRenderMetadata(undefined)
  /** 主表数据。 */
  data: Record<string, unknown> = {}
  /** 明细数据（页签键 → 行集合）。 */
  details: Record<string, Record<string, unknown>[]> = {}
  /** 字段权限标记。 */
  permissions: Record<string, FieldPermission> = {}
  /** 件层字段覆盖。 */
  overrides: Record<string, FieldRenderOverride> = {}
  /** 主表校验错误。 */
  errors: FormRenderError[] = []
  /** 明细行级校验错误。 */
  detailErrors: DetailRenderError[] = []
  /** 当前阶段。 */
  phase: RendererPhase = 'idle'
  /** 失败文案。 */
  errorMessage = ''
  /** 记录版本（乐观锁）。 */
  recordVersion: number | undefined
  /** 注入的处理函数集。 */
  jobs: FormRendererJobs = {}
  /** 权限上下文。 */
  access: BaseAccess | undefined
  /** 提示通知协作者。 */
  notice: BaseNotice | undefined
  /** 表单元数据能力（组合；未注入即跳过）。 */
  formMeta: BaseFormMeta | undefined
  /** 字段权限能力（组合；未注入即不叠加）。 */
  fieldPerm: BaseFieldPerm | undefined
  /** 校验能力（组合；未注入即用领域规则）。 */
  validatable: BaseValidatable | undefined

  /** 是否处于占位（降级）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否只读（占位 / 强制只读 / 查看态 / 无渲染权限）。 */
  get readonly(): boolean {
    if (this.degraded || this.forceReadOnly || this.mode === 'view') {
      return true
    }
    return !this.hasRenderPerm()
  }

  /** 是否进行中。 */
  get busy(): boolean {
    return this.phase === 'loading' || this.phase === 'submitting'
  }

  /** 渲染计划（纯派生，任何状态变更即最新）。 */
  get plan(): RenderPlan {
    return buildRenderPlan(this.meta, {
      mode: this.mode,
      forceReadOnly: this.forceReadOnly,
      data: this.data,
      permissions: this.effectivePermissions(),
      overrides: this.overrides,
    })
  }

  /** 主表字段项（摊平）。 */
  get fields(): RenderFieldPlan[] {
    return this.plan.sections.flatMap((section) => section.fields)
  }

  /** 明细列。 */
  get detailColumns(): RenderDetailColumn[] {
    return this.plan.detailColumns
  }

  /** 主表校验结果（纯派生）。 */
  get validation(): FormValidationResult {
    const errors = this.errors.filter((error) => this.fields.some((field) => field.key === error.field))
    return {
      valid: errors.length === 0,
      errors,
      firstField: errors[0]?.field,
      message: errors.length === 0 ? '' : errors.map((error) => `${error.field}：${error.message}`).join('；'),
    }
  }

  /** 明细校验结果（纯派生）。 */
  get detailValidation(): DetailValidationResult {
    return {
      valid: this.detailErrors.length === 0,
      errors: this.detailErrors,
      message: this.detailErrors.length === 0 ? '' : this.detailErrors.map((error) => error.message).join('；'),
    }
  }

  /** 是否可提交。 */
  get canSubmit(): boolean {
    return isSubmitAllowed({
      readonly: this.readonly,
      busy: this.busy,
      validation: this.validation,
      detailValidation: this.detailValidation,
    })
  }

  /** 失效字段引用（已跳过渲染）。 */
  get unknownFields(): string[] {
    return this.plan.unknownFields
  }

  /** 停用 / 建列失败字段（只读保留）。 */
  get disabledFields(): string[] {
    return this.plan.disabledFields
  }

  /** 是否可写入（占位 / 强制只读 / 无渲染权限均不可写；`view` 态由字段权限终态决定）。 */
  get writable(): boolean {
    if (this.degraded || this.forceReadOnly) {
      return false
    }
    return this.hasRenderPerm()
  }

  /**
   * 是否持渲染权限（未注入权限上下文视为有权，后端兜底）。
   */
  protected hasRenderPerm(): boolean {
    return this.access === undefined || this.access.has(FORM_RENDER_PERM)
  }

  /**
   * 生效字段权限（字段权限能力承载整体收紧；下发标记逐字段覆盖）。
   *
   * 全局项只取「收紧 / 显式开启」方向（`visible=false` / `editable=false` / `required=true` / `mask=true`），
   * 避免把字段自身属性误覆盖为缺省值。
   */
  protected effectivePermissions(): Record<string, FieldPermission> {
    if (this.fieldPerm === undefined) {
      return this.permissions
    }
    const global: FieldPermission = {}
    if (!this.fieldPerm.permVisible) {
      global.visible = false
    }
    if (!this.fieldPerm.editable) {
      global.editable = false
    }
    if (this.fieldPerm.permRequired) {
      global.required = true
    }
    if (this.fieldPerm.masked) {
      global.mask = true
    }
    if (Object.keys(global).length === 0) {
      return this.permissions
    }
    const result: Record<string, FieldPermission> = {}
    for (const field of this.meta.fields) {
      result[field.key] = { ...global, ...(this.permissions[field.key] ?? {}) }
    }
    return result
  }

  /**
   * 设置就绪态。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    this.ready = value
    this.notifyLifecycle('update')
  }

  /**
   * 注入处理函数集（整体替换；未注入的项按占位）。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: FormRendererJobs): void {
    this.jobs = jobs
    this.notifyLifecycle('update')
  }

  /**
   * 注入权限上下文（`undefined` 表示不注入）。
   *
   * @param access 权限上下文。
   */
  setAccess(access: BaseAccess | undefined): void {
    this.access = access
    this.notifyLifecycle('update')
  }

  /**
   * 注入提示通知协作者。
   *
   * @param notice 提示通知。
   */
  setNotice(notice: BaseNotice | undefined): void {
    this.notice = notice
    this.notifyLifecycle('update')
  }

  /**
   * 注入表单元数据能力。
   *
   * @param meta 表单元数据能力。
   */
  setFormMeta(meta: BaseFormMeta | undefined): void {
    this.formMeta = meta
    this.notifyLifecycle('update')
  }

  /**
   * 注入字段权限能力。
   *
   * @param perm 字段权限能力。
   */
  setFieldPerm(perm: BaseFieldPerm | undefined): void {
    this.fieldPerm = perm
    this.notifyLifecycle('update')
  }

  /**
   * 注入校验能力。
   *
   * @param validatable 校验能力。
   */
  setValidatable(validatable: BaseValidatable | undefined): void {
    this.validatable = validatable
    this.notifyLifecycle('update')
  }

  /**
   * 设置三态（不改数据、不校验、不请求）。
   *
   * @param mode 三态。
   */
  setMode(mode: unknown): boolean {
    const next = normalizeRenderMode(mode)
    if (next === this.mode) {
      return false
    }
    this.mode = next
    this.errors = []
    this.detailErrors = []
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 切换表单（清空元数据与数据，不自动取数）。
   *
   * @param formCode 表单标识。
   */
  setFormCode(formCode: string): boolean {
    if (formCode === this.formCode) {
      return false
    }
    this.formCode = formCode
    this.meta = normalizeRenderMetadata(undefined)
    this.data = {}
    this.details = {}
    this.recordVersion = undefined
    this.errors = []
    this.detailErrors = []
    this.phase = 'idle'
    this.errorMessage = ''
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置记录主键（清空数据，不自动取数）。
   *
   * @param recordId 记录主键。
   */
  setRecordId(recordId: string | number | undefined): void {
    if (recordId === this.recordId) {
      return
    }
    this.recordId = recordId
    this.data = {}
    this.details = {}
    this.recordVersion = undefined
    this.errors = []
    this.detailErrors = []
    this.phase = 'idle'
    this.notifyLifecycle('update')
  }

  /**
   * 设置强制只读。
   *
   * @param value 是否强制只读。
   */
  setForceReadOnly(value: boolean): void {
    this.forceReadOnly = value
    this.notifyLifecycle('update')
  }

  /**
   * 设置字段权限标记（整体替换）。
   *
   * @param permissions 权限标记。
   */
  setPermissions(permissions: Readonly<Record<string, FieldPermission>> | undefined): void {
    this.permissions = { ...(permissions ?? {}) }
    this.notifyLifecycle('update')
  }

  /**
   * 设置件层字段覆盖（整体替换）。
   *
   * @param overrides 覆盖集合。
   */
  setOverrides(overrides: Readonly<Record<string, FieldRenderOverride>> | undefined): void {
    this.overrides = { ...(overrides ?? {}) }
    this.notifyLifecycle('update')
  }

  /**
   * 设置渲染元数据（装载入口：归一为运行态）。
   *
   * @param input 装载输入或生效布局。
   */
  setMeta(input: RenderMetadataInput | LayoutEffective | undefined): void {
    this.meta = normalizeRenderMetadata(input)
    if (this.meta.permissions !== undefined) {
      this.permissions = { ...this.meta.permissions }
    }
    this.notifyLifecycle('update')
  }

  /**
   * 设置主表数据（整体替换）。
   *
   * @param data 主表数据。
   */
  setData(data: Record<string, unknown> | undefined): void {
    this.data = { ...(data ?? {}) }
    this.notifyLifecycle('update')
  }

  /**
   * 设置明细数据（整体替换；缺省页签补空数组）。
   *
   * @param details 明细数据。
   */
  setDetails(details: DetailDataSet | undefined): void {
    const next: Record<string, Record<string, unknown>[]> = {}
    for (const [key, rows] of Object.entries(details ?? {})) {
      next[key] = rows.map((row) => ({ ...row }))
    }
    this.details = next
    this.notifyLifecycle('update')
  }

  /**
   * 写入字段值（只读 / 不可编辑不动作；写入后即时校验该字段）。
   *
   * @param fieldKey 字段键。
   * @param value 值。
   */
  setFieldValue(fieldKey: string, value: unknown): boolean {
    if (!this.writable) {
      return false
    }
    const item = this.fields.find((field) => field.key === fieldKey)
    if (item === undefined || !item.editable) {
      return false
    }
    this.data = { ...this.data, [fieldKey]: value }
    this.applyFieldError(fieldKey, value)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 读取字段值（缺省回落默认值）。
   *
   * @param fieldKey 字段键。
   */
  getFieldValue(fieldKey: string): unknown {
    if (fieldKey in this.data) {
      return this.data[fieldKey]
    }
    return this.fields.find((field) => field.key === fieldKey)?.defaultValue
  }

  /**
   * 整体替换明细行（只读不动作）。
   *
   * @param detailKey 明细页签键。
   * @param rows 行集合。
   */
  setDetailRows(detailKey: string, rows: readonly unknown[]): boolean {
    if (!this.writable) {
      return false
    }
    this.details = { ...this.details, [detailKey]: normalizeRows(rows) }
    this.detailErrors = this.detailErrors.filter((error) => error.detailKey !== detailKey)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 追加明细行（只读不动作）。
   *
   * @param detailKey 明细页签键。
   * @param row 初始行（可选）。
   */
  addDetailRow(detailKey: string, row: Record<string, unknown> = {}): boolean {
    if (!this.writable) {
      return false
    }
    const rows = [...(this.details[detailKey] ?? []), { ...row }]
    this.details = { ...this.details, [detailKey]: rows }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 移除明细行（越界 / 只读不动作）。
   *
   * @param detailKey 明细页签键。
   * @param index 行下标。
   */
  removeDetailRow(detailKey: string, index: number): boolean {
    if (!this.writable) {
      return false
    }
    const rows = this.details[detailKey]
    if (rows === undefined || index < 0 || index >= rows.length) {
      return false
    }
    this.details = { ...this.details, [detailKey]: rows.filter((_, position) => position !== index) }
    this.detailErrors = this.detailErrors.filter((error) => !(error.detailKey === detailKey && error.index === index))
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 写入明细单元格（只读 / 不可编辑不动作；写入后即时校验该行）。
   *
   * @param detailKey 明细页签键。
   * @param index 行下标。
   * @param fieldKey 字段键。
   * @param value 值。
   */
  setDetailCell(detailKey: string, index: number, fieldKey: string, value: unknown): boolean {
    if (!this.writable) {
      return false
    }
    const column = this.plan.detailColumns.find((item) => item.key === fieldKey)
    if (column === undefined || !column.editable) {
      return false
    }
    const rows = this.details[detailKey]
    if (rows === undefined || index < 0 || index >= rows.length) {
      return false
    }
    const next = rows.map((row, position) => (position === index ? { ...row, [fieldKey]: value } : row))
    this.details = { ...this.details, [detailKey]: next }
    this.applyDetailErrors(detailKey, index, next[index] ?? {})
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 全量校验（主表 + 全部明细行）。
   */
  validate(): FormValidationResult {
    const result = this.computeValidation()
    this.errors = result.errors
    this.detailErrors = this.computeDetailErrors()
    this.errorMessage = result.valid ? '' : result.message
    this.notifyLifecycle('update')
    return result
  }

  /**
   * 单字段即时校验（返回错误文案或 `undefined`）。
   *
   * @param fieldKey 字段键。
   */
  validateField(fieldKey: string): string | undefined {
    const item = this.fields.find((field) => field.key === fieldKey)
    if (item === undefined || !item.visible || !item.editable) {
      return undefined
    }
    const value = fieldKey in this.data ? this.data[fieldKey] : item.value
    return validatePlanField(item, value)
  }

  /** 重置（清空数据、明细与错误，数据通路与元数据保留）。 */
  reset(): void {
    this.data = {}
    this.details = {}
    this.errors = []
    this.detailErrors = []
    this.errorMessage = ''
    this.phase = 'idle'
    this.notifyLifecycle('update')
  }

  /**
   * 取数（未就绪 / 未注入处理函数时占位不动作）。
   */
  async load(): Promise<LayoutEffective | undefined> {
    if (this.degraded || this.jobs.loadLayout === undefined || this.busy) {
      return undefined
    }
    this.phase = 'loading'
    this.errorMessage = ''
    this.requestCount += 1
    this.notifyLifecycle('update')
    try {
      if (this.formMeta !== undefined) {
        await this.formMeta.load()
      }
      const loaded = await this.jobs.loadLayout({
        formCode: this.formCode,
        mode: this.mode,
        recordId: this.recordId,
      })
      this.setMeta(loaded)
      if (this.mode !== 'create' && this.recordId !== undefined && this.jobs.loadRecord !== undefined) {
        this.requestCount += 1
        const snapshot = await this.jobs.loadRecord({ formCode: this.formCode, recordId: this.recordId })
        if (snapshot !== undefined) {
          this.data = { ...(snapshot.data ?? {}) }
          this.details = normalizeDetailMap(snapshot.details)
          this.recordVersion = snapshot.recordVersion
        }
      }
      this.phase = 'done'
      this.notifyLifecycle('update')
      return this.meta
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormRenderer.load' })
      this.notifyLifecycle('update')
      return undefined
    }
  }

  /**
   * 提交（校验不通过 / 未注入处理函数时不请求；主从单事务）。
   */
  async submit(): Promise<SubmitResult | undefined> {
    if (this.readonly || this.busy) {
      return undefined
    }
    const result = this.validate()
    if (!result.valid || !this.detailValidation.valid) {
      this.phase = 'failed'
      this.notifyLifecycle('update')
      return undefined
    }
    if (this.jobs.submit === undefined) {
      return undefined
    }
    this.phase = 'submitting'
    this.errorMessage = ''
    this.requestCount += 1
    this.notifyLifecycle('update')
    try {
      const payload = buildSubmitPayload({
        formCode: this.formCode,
        mode: this.mode,
        recordId: this.recordId,
        recordVersion: this.recordVersion,
        plan: this.plan,
        data: this.data,
        details: this.details,
      })
      const submitted = await this.jobs.submit(payload)
      this.recordVersion = submitted?.recordVersion ?? this.recordVersion
      this.errors = []
      this.detailErrors = []
      this.phase = 'done'
      this.notifyLifecycle('update')
      return submitted
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormRenderer.submit' })
      this.notifyLifecycle('update')
      return undefined
    }
  }

  /**
   * 重试提交（以当前数据重放；未注入 / 只读 / 进行中不动作）。
   */
  async retry(): Promise<SubmitResult | undefined> {
    return this.submit()
  }

  /** 计算主表校验结果。 */
  private computeValidation(): FormValidationResult {
    const errors: FormRenderError[] = []
    for (const item of this.fields) {
      if (!item.visible) {
        continue
      }
      const value = item.key in this.data ? this.data[item.key] : item.value
      const message = validatePlanField(item, value)
      if (message !== undefined) {
        errors.push({ field: item.key, message })
      }
    }
    return {
      valid: errors.length === 0,
      errors,
      firstField: errors[0]?.field,
      message: errors.length === 0 ? '' : errors.map((error) => `${error.field}：${error.message}`).join('；'),
    }
  }

  /** 即时更新单字段错误（通过即清）。 */
  private applyFieldError(fieldKey: string, value: unknown): void {
    const item = this.fields.find((field) => field.key === fieldKey)
    const message = item === undefined ? undefined : validatePlanField(item, value)
    const rest = this.errors.filter((error) => error.field !== fieldKey)
    this.errors = message === undefined ? rest : [...rest, { field: fieldKey, message }]
  }

  /** 计算明细错误（全部页签行级校验）。 */
  private computeDetailErrors(): DetailRenderError[] {
    const errors: DetailRenderError[] = []
    const columns = this.plan.detailColumns
    for (const [detailKey, rows] of Object.entries(this.details)) {
      rows.forEach((row, index) => {
        for (const column of columns) {
          const base = column.base
          if (base === undefined || !column.editable) {
            continue
          }
          const message = validatePlanField(baseToPlan(base, column), row[column.key])
          if (message !== undefined) {
            errors.push({
              detailKey,
              index,
              field: column.key,
              message: `第 ${index + 1} 行 ${column.title}：${message}`,
            })
          }
        }
      })
    }
    return errors
  }

  /** 即时更新单行明细错误。 */
  private applyDetailErrors(detailKey: string, index: number, row: Record<string, unknown>): void {
    const rest = this.detailErrors.filter((error) => !(error.detailKey === detailKey && error.index === index))
    const added: DetailRenderError[] = []
    for (const column of this.plan.detailColumns) {
      const base = column.base
      if (base === undefined || !column.editable) {
        continue
      }
      const message = validatePlanField(baseToPlan(base, column), row[column.key])
      if (message !== undefined) {
        added.push({
          detailKey,
          index,
          field: column.key,
          message: `第 ${index + 1} 行 ${column.title}：${message}`,
        })
      }
    }
    this.detailErrors = [...rest, ...added]
  }
}

/** 归一明细映射（保留引用结构，值为行拷贝）。 */
function normalizeDetailMap(details: DetailDataSet | undefined): Record<string, Record<string, unknown>[]> {
  const result: Record<string, Record<string, unknown>[]> = {}
  for (const [key, rows] of Object.entries(details ?? {})) {
    result[key] = normalizeRows(rows)
  }
  return result
}

/** 归一行集合（剔除非对象行）。 */
function normalizeRows(rows: readonly unknown[]): Record<string, unknown>[] {
  const result: Record<string, unknown>[] = []
  for (const row of rows) {
    if (row === null || row === undefined || typeof row !== 'object' || Array.isArray(row)) {
      continue
    }
    result.push({ ...(row as Record<string, unknown>) })
  }
  return result
}

/** 计划项规则校验（规则链复用领域编译 + 选项集在范围内校验）。 */
function validatePlanField(item: RenderFieldPlan, value: unknown): string | undefined {
  for (const validator of compileFieldRules(item.rules)) {
    const message = validator(value)
    if (message !== undefined) {
      return message
    }
  }
  const empty = value == null || value === '' || (Array.isArray(value) && value.length === 0)
  if (item.options.length > 0 && !empty) {
    const allowed = new Set(item.options.map((option) => option.value))
    const values = Array.isArray(value) ? value : [value]
    if (!values.every((entry) => allowed.has(String(entry)))) {
      return '选项不在可选范围内'
    }
  }
  return undefined
}

/** 明细列 → 字段计划（供行级校验复用同一套规则与必填口径）。 */
function baseToPlan(base: FormField, column: RenderDetailColumn): RenderFieldPlan {
  const rules: RenderFieldPlan['rules'] = []
  if (base.required === true && column.editable) {
    rules.push({ kind: 'required' })
  }
  rules.push(...(base.rules ?? []))
  return {
    key: base.key,
    label: base.label,
    widget: 'text',
    unknown: false,
    colSpan: false,
    placeholder: '',
    defaultValue: undefined,
    options: [...(base.options ?? [])],
    rules,
    value: undefined,
    visible: true,
    editable: column.editable,
    disabled: !column.editable,
    required: base.required === true,
    masked: false,
    displayOnly: false,
    base,
  }
}
