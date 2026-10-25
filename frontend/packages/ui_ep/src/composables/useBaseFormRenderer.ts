/** 表单渲染器投影：把核心渲染编排能力基类 `BaseFormRenderer` 投影为组合式（三态 / 计划 / 校验 / 明细 / 提交）。 */

import type {
  BaseAccess,
  BaseFieldPerm,
  BaseFormMeta,
  BaseNotice,
  BaseValidatable,
  DetailDataSet,
  DetailRenderError,
  FieldPermission,
  FieldRenderOverride,
  FormRendererJobs,
  FormRenderMode,
  FormValidationResult,
  LayoutEffective,
  RenderDetailColumn,
  RenderFieldPlan,
  RenderMetadataInput,
  RenderPlan,
  RendererPhase,
  SubmitResult,
} from '@bms/core'
import { BaseFormRenderer } from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体表单渲染器（可实例化）。 */
class FormRendererState extends BaseFormRenderer {}

/** 选项。 */
export interface UseBaseFormRendererOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 表单标识。 */
  formCode?: string
  /** 三态（缺省 `create`）。 */
  mode?: FormRenderMode
  /** 记录主键。 */
  recordId?: string | number
  /** 强制只读。 */
  forceReadOnly?: boolean
  /** 布局元数据（装载输入或生效布局）。 */
  meta?: RenderMetadataInput | LayoutEffective
  /** 主表数据。 */
  data?: Record<string, unknown>
  /** 明细数据。 */
  details?: DetailDataSet
  /** 字段权限标记。 */
  permissions?: Readonly<Record<string, FieldPermission>>
  /** 件层字段覆盖。 */
  overrides?: Readonly<Record<string, FieldRenderOverride>>
  /** 注入的处理函数集。 */
  jobs?: FormRendererJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 表单元数据能力。 */
  formMeta?: BaseFormMeta
  /** 字段权限能力。 */
  fieldPerm?: BaseFieldPerm
  /** 校验能力。 */
  validatable?: BaseValidatable
}

/** `useBaseFormRenderer` 返回面。 */
export interface UseBaseFormRendererResult {
  /** 渲染器基类实例（跨实例经 `markRaw` 隔离）。 */
  renderer: BaseFormRenderer
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 是否只读（响应式）。 */
  readonly: Ref<boolean>
  /** 是否可写入（响应式）。 */
  writable: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<RendererPhase>
  /** 三态（响应式）。 */
  mode: Ref<FormRenderMode>
  /** 渲染计划（响应式）。 */
  plan: Ref<RenderPlan>
  /** 主表字段项（响应式）。 */
  fields: Ref<RenderFieldPlan[]>
  /** 明细列（响应式）。 */
  detailColumns: Ref<RenderDetailColumn[]>
  /** 主表数据（响应式）。 */
  data: Ref<Record<string, unknown>>
  /** 明细数据（响应式）。 */
  details: Ref<Record<string, Record<string, unknown>[]>>
  /** 主表错误（响应式）。 */
  errors: Ref<FormValidationResult['errors']>
  /** 明细行级错误（响应式）。 */
  detailErrors: Ref<DetailRenderError[]>
  /** 主表校验结果（响应式）。 */
  validation: Ref<FormValidationResult>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 设置就绪态。 */
  setReady: (value: boolean) => void
  /** 切换三态。 */
  setMode: (mode: unknown) => boolean
  /** 切换表单。 */
  setFormCode: (formCode: string) => boolean
  /** 设置记录主键。 */
  setRecordId: (recordId: string | number | undefined) => void
  /** 设置强制只读。 */
  setForceReadOnly: (value: boolean) => void
  /** 装载渲染元数据。 */
  setMeta: (input: RenderMetadataInput | LayoutEffective | undefined) => void
  /** 设置主表数据。 */
  setData: (data: Record<string, unknown> | undefined) => void
  /** 设置明细数据。 */
  setDetails: (details: DetailDataSet | undefined) => void
  /** 设置字段权限标记。 */
  setPermissions: (permissions: Readonly<Record<string, FieldPermission>> | undefined) => void
  /** 设置件层字段覆盖。 */
  setOverrides: (overrides: Readonly<Record<string, FieldRenderOverride>> | undefined) => void
  /** 注入处理函数集。 */
  setJobs: (jobs: FormRendererJobs) => void
  /** 写入字段值。 */
  setFieldValue: (fieldKey: string, value: unknown) => boolean
  /** 读取字段值。 */
  getFieldValue: (fieldKey: string) => unknown
  /** 整体替换明细行。 */
  setDetailRows: (detailKey: string, rows: readonly unknown[]) => boolean
  /** 追加明细行。 */
  addDetailRow: (detailKey: string, row?: Record<string, unknown>) => boolean
  /** 移除明细行。 */
  removeDetailRow: (detailKey: string, index: number) => boolean
  /** 写入明细单元格。 */
  setDetailCell: (detailKey: string, index: number, fieldKey: string, value: unknown) => boolean
  /** 全量校验。 */
  validate: () => FormValidationResult
  /** 单字段即时校验。 */
  validateField: (fieldKey: string) => string | undefined
  /** 取数。 */
  load: () => Promise<LayoutEffective | undefined>
  /** 提交。 */
  submit: () => Promise<SubmitResult | undefined>
  /** 重试提交。 */
  retry: () => Promise<SubmitResult | undefined>
  /** 重置。 */
  reset: () => void
}

/**
 * 使用表单渲染器投影。
 *
 * @param options 选项。
 * @returns 渲染器基类实例与响应式面。
 */
export function useBaseFormRenderer(options: UseBaseFormRendererOptions = {}): UseBaseFormRendererResult {
  const renderer = new FormRendererState()
  // 跨实例基类对象经 props 进响应式会读取私有字段报错，统一 `markRaw(toRaw(x))` 隔离。
  if (options.access !== undefined) {
    renderer.setAccess(markRaw(toRaw(options.access)))
  }
  if (options.notice !== undefined) {
    renderer.setNotice(markRaw(toRaw(options.notice)))
  }
  if (options.formMeta !== undefined) {
    renderer.setFormMeta(markRaw(toRaw(options.formMeta)))
  }
  if (options.fieldPerm !== undefined) {
    renderer.setFieldPerm(markRaw(toRaw(options.fieldPerm)))
  }
  if (options.validatable !== undefined) {
    renderer.setValidatable(markRaw(toRaw(options.validatable)))
  }
  if (options.jobs !== undefined) {
    renderer.setJobs(options.jobs)
  }
  if (options.formCode !== undefined) {
    renderer.setFormCode(options.formCode)
  }
  if (options.mode !== undefined) {
    renderer.setMode(options.mode)
  }
  if (options.recordId !== undefined) {
    renderer.setRecordId(options.recordId)
  }
  renderer.setForceReadOnly(options.forceReadOnly ?? false)
  if (options.meta !== undefined) {
    renderer.setMeta(options.meta)
  }
  if (options.data !== undefined) {
    renderer.setData(options.data)
  }
  if (options.details !== undefined) {
    renderer.setDetails(options.details)
  }
  if (options.permissions !== undefined) {
    renderer.setPermissions(options.permissions)
  }
  if (options.overrides !== undefined) {
    renderer.setOverrides(options.overrides)
  }
  renderer.setReady(options.ready ?? false)

  const ready = ref(renderer.ready)
  const degraded = ref(renderer.degraded)
  const readonly = ref(renderer.readonly)
  const writable = ref(renderer.writable)
  const busy = ref(renderer.busy)
  const phase = ref<RendererPhase>(renderer.phase)
  const mode = ref<FormRenderMode>(renderer.mode)
  const plan = ref<RenderPlan>(renderer.plan)
  const fields = ref<RenderFieldPlan[]>(renderer.fields)
  const detailColumns = ref<RenderDetailColumn[]>(renderer.detailColumns)
  const data = ref<Record<string, unknown>>({ ...renderer.data })
  const details = ref<Record<string, Record<string, unknown>[]>>({ ...renderer.details })
  const errors = ref<FormValidationResult['errors']>([...renderer.errors])
  const detailErrors = ref<DetailRenderError[]>([...renderer.detailErrors])
  const validation = ref<FormValidationResult>(renderer.validation)
  const errorMessage = ref(renderer.errorMessage)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = renderer.ready
    degraded.value = renderer.degraded
    readonly.value = renderer.readonly
    writable.value = renderer.writable
    busy.value = renderer.busy
    phase.value = renderer.phase
    mode.value = renderer.mode
    plan.value = renderer.plan
    fields.value = renderer.fields
    detailColumns.value = renderer.detailColumns
    data.value = { ...renderer.data }
    details.value = { ...renderer.details }
    errors.value = [...renderer.errors]
    detailErrors.value = [...renderer.detailErrors]
    validation.value = renderer.validation
    errorMessage.value = renderer.errorMessage
  }

  const off = renderer.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    renderer,
    ready,
    degraded,
    readonly,
    writable,
    busy,
    phase,
    mode,
    plan,
    fields,
    detailColumns,
    data,
    details,
    errors,
    detailErrors,
    validation,
    errorMessage,
    setReady: (value) => {
      renderer.setReady(value)
      sync()
    },
    setMode: (next) => {
      const changed = renderer.setMode(next)
      sync()
      return changed
    },
    setFormCode: (formCode) => {
      const changed = renderer.setFormCode(formCode)
      sync()
      return changed
    },
    setRecordId: (recordId) => {
      renderer.setRecordId(recordId)
      sync()
    },
    setForceReadOnly: (value) => {
      renderer.setForceReadOnly(value)
      sync()
    },
    setMeta: (input) => {
      renderer.setMeta(input)
      sync()
    },
    setData: (next) => {
      renderer.setData(next)
      sync()
    },
    setDetails: (next) => {
      renderer.setDetails(next)
      sync()
    },
    setPermissions: (next) => {
      renderer.setPermissions(next)
      sync()
    },
    setOverrides: (next) => {
      renderer.setOverrides(next)
      sync()
    },
    setJobs: (jobs) => {
      renderer.setJobs(jobs)
      sync()
    },
    setFieldValue: (fieldKey, value) => {
      const changed = renderer.setFieldValue(fieldKey, value)
      sync()
      return changed
    },
    getFieldValue: (fieldKey) => renderer.getFieldValue(fieldKey),
    setDetailRows: (detailKey, rows) => {
      const changed = renderer.setDetailRows(detailKey, rows)
      sync()
      return changed
    },
    addDetailRow: (detailKey, row) => {
      const changed = renderer.addDetailRow(detailKey, row)
      sync()
      return changed
    },
    removeDetailRow: (detailKey, index) => {
      const changed = renderer.removeDetailRow(detailKey, index)
      sync()
      return changed
    },
    setDetailCell: (detailKey, index, fieldKey, value) => {
      const changed = renderer.setDetailCell(detailKey, index, fieldKey, value)
      sync()
      return changed
    },
    validate: () => {
      const result = renderer.validate()
      sync()
      return result
    },
    validateField: (fieldKey) => renderer.validateField(fieldKey),
    load: async () => {
      const result = await renderer.load()
      sync()
      return result
    },
    submit: async () => {
      const result = await renderer.submit()
      sync()
      return result
    },
    retry: async () => {
      const result = await renderer.retry()
      sync()
      return result
    },
    reset: () => {
      renderer.reset()
      sync()
    },
  }
}
