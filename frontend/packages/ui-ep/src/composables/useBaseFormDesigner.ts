/** 表单设计器投影：把核心能力基类 `BaseFormDesigner` 投影为组合式（布局 / 层级 / 脏基线 / 保存发布）。 */

import {
  BaseFormDesigner,
  type BaseAccess,
  type BaseDragDrop,
  type BaseFormMeta,
  type BaseNotice,
  type DesignerBlockAction,
  type DesignerDropInput,
  type DesignerExtFieldResult,
  type DesignerJobs,
  type DesignerLevel,
  type DesignerPhase,
  type DesignerSaveResult,
  type DesignerSelection,
  type DesignerSnapshot,
  type ExtFieldDraft,
  type FormField,
  type FormLayout,
  type FormLayoutLevels,
  type LayoutLabelPosition,
  type LayoutDetailColumnInput,
  type LayoutEffective,
  type LayoutValidationResult,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体表单设计器件（可实例化）。 */
class FormDesignerState extends BaseFormDesigner {}

/** 选项。 */
export interface UseBaseFormDesignerOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 表单标识。 */
  formCode?: string
  /** 当前层级（缺省 `tenant`）。 */
  level?: DesignerLevel
  /** 角色标识（角色视图）。 */
  roleId?: string
  /** 外部强制只读。 */
  readOnly?: boolean
  /** 合并字段清单。 */
  fields?: readonly FormField[]
  /** 当前层级布局。 */
  layout?: FormLayout
  /** 三级层级布局。 */
  levels?: FormLayoutLevels
  /** 注入的处理函数集（未注入即占位）。 */
  jobs?: DesignerJobs
  /** 权限上下文（未注入视为有权）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 表单元数据能力（组合）。 */
  formMeta?: BaseFormMeta
  /** 拖拽能力（组合；未注入仍完成落点）。 */
  drag?: BaseDragDrop
  /** 已注册字段类型（空数组视为不限）。 */
  registeredTypes?: readonly string[]
}

/** `useBaseFormDesigner` 返回面。 */
export interface UseBaseFormDesignerResult {
  /** 设计器基类实例。 */
  designer: BaseFormDesigner
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 是否只读（响应式）。 */
  readonly: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<DesignerPhase>
  /** 当前工作布局（响应式）。 */
  layout: Ref<FormLayout>
  /** 合并字段清单（响应式）。 */
  fields: Ref<FormField[]>
  /** 画布选中对象（响应式）。 */
  selected: Ref<DesignerSelection | null>
  /** 是否脏（响应式）。 */
  dirty: Ref<boolean>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 自建字段校验失败文案（响应式）。 */
  fieldError: Ref<string>
  /** 布局校验结果（响应式）。 */
  validation: Ref<LayoutValidationResult>
  /** 失效字段引用（响应式）。 */
  unknownFields: Ref<string[]>
  /** 重复引用字段（响应式）。 */
  duplicateFields: Ref<string[]>
  /** 渲染输入（响应式；与渲染器同一份元数据）。 */
  renderMetadata: Ref<LayoutEffective>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 切换表单（脏数据时不切换并返回 `false`）。 */
  setFormCode: (formCode: string) => boolean
  /** 切换层级。 */
  setLevel: (level: DesignerLevel, roleId?: string) => boolean
  /** 设置字段清单。 */
  setFields: (fields: readonly FormField[]) => void
  /** 设置三级层级布局（装载入口）。 */
  setLayouts: (levels?: FormLayoutLevels) => void
  /** 注入处理函数集。 */
  setJobs: (jobs: DesignerJobs) => void
  /** 设置画布选中对象。 */
  select: (target: DesignerSelection | null) => void
  /** 新增字段入画布。 */
  addField: (fieldKey: string, sectionKey?: string) => boolean
  /** 拖拽落点。 */
  moveField: (input: DesignerDropInput) => boolean
  /** 移出字段。 */
  removeField: (fieldKey: string) => boolean
  /** 翻转跨列。 */
  toggleColSpan: (fieldKey: string) => boolean
  /** 设置分区列数。 */
  setColumns: (sectionKey: string, columns: unknown) => boolean
  /** 新增分区（返回新分区键）。 */
  addSection: () => string
  /** 删除分区。 */
  removeSection: (sectionKey: string) => boolean
  /** 重命名分区。 */
  renameSection: (sectionKey: string, title: string) => boolean
  /** 设置标签位置。 */
  setLabelPosition: (position: LayoutLabelPosition) => boolean
  /** 设置标签宽度。 */
  setLabelWidth: (width: unknown) => boolean
  /** 设置查询区字段。 */
  setQueryFields: (keys: readonly (string | number)[]) => boolean
  /** 设置明细列。 */
  setDetailColumns: (columns: readonly LayoutDetailColumnInput[]) => boolean
  /** 记脏基线。 */
  markBaseline: () => void
  /** 撤销未保存变更。 */
  discard: () => boolean
  /** 是否需要拦截。 */
  needsBlock: (action: DesignerBlockAction) => boolean
  /** 取数。 */
  load: () => Promise<DesignerSnapshot | undefined>
  /** 保存。 */
  save: () => Promise<DesignerSaveResult | undefined>
  /** 发布。 */
  publish: () => Promise<boolean>
  /** 恢复默认。 */
  restoreDefault: () => Promise<boolean>
  /** 新建自建字段。 */
  createField: (draft: ExtFieldDraft) => Promise<DesignerExtFieldResult | undefined>
  /** DDL 重试。 */
  retryField: (fieldKey: string) => Promise<DesignerExtFieldResult | undefined>
}

/**
 * 使用表单设计器投影。
 *
 * @param options 选项。
 * @returns 设计器基类实例与响应式面。
 */
export function useBaseFormDesigner(options: UseBaseFormDesignerOptions = {}): UseBaseFormDesignerResult {
  const designer = new FormDesignerState()
  if (options.formCode !== undefined) {
    designer.setFormCode(options.formCode)
  }
  if (options.level !== undefined) {
    designer.setLevel(options.level, options.roleId)
  } else if (options.roleId !== undefined) {
    designer.roleId = options.roleId
  }
  if (options.fields !== undefined) {
    designer.setFields(options.fields)
  }
  if (options.levels !== undefined) {
    designer.setLayouts(options.levels)
  } else if (options.layout !== undefined) {
    designer.setLayouts({ [designer.level]: options.layout })
  }
  if (options.jobs !== undefined) {
    designer.jobs = options.jobs
  }
  if (options.access !== undefined) {
    designer.access = markRaw(toRaw(options.access))
  }
  if (options.notice !== undefined) {
    designer.notice = markRaw(toRaw(options.notice))
  }
  if (options.formMeta !== undefined) {
    designer.formMeta = markRaw(toRaw(options.formMeta))
  }
  if (options.drag !== undefined) {
    designer.drag = markRaw(toRaw(options.drag))
  }
  if (options.registeredTypes !== undefined) {
    designer.setRegisteredTypes(options.registeredTypes)
  }
  designer.setReady(options.ready ?? false)

  const ready = ref(designer.ready)
  const degraded = ref(designer.degraded)
  const readonly = ref(designer.readonly)
  const busy = ref(designer.busy)
  const phase = ref<DesignerPhase>(designer.phase)
  const layout = ref<FormLayout>(designer.layout)
  const fields = ref<FormField[]>([...designer.fields])
  const selected = ref<DesignerSelection | null>(designer.selected)
  const dirty = ref(designer.dirty)
  const errorMessage = ref(designer.errorMessage)
  const fieldError = ref(designer.fieldError)
  const validation = ref<LayoutValidationResult>(designer.validation)
  const unknownFields = ref<string[]>(designer.unknownFields)
  const duplicateFields = ref<string[]>(designer.duplicateFields)
  const renderMetadata = ref<LayoutEffective>(designer.renderMetadata)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = designer.ready
    degraded.value = designer.degraded
    readonly.value = designer.readonly
    busy.value = designer.busy
    phase.value = designer.phase
    layout.value = designer.layout
    fields.value = [...designer.fields]
    selected.value = designer.selected
    dirty.value = designer.dirty
    errorMessage.value = designer.errorMessage
    fieldError.value = designer.fieldError
    validation.value = designer.validation
    unknownFields.value = designer.unknownFields
    duplicateFields.value = designer.duplicateFields
    renderMetadata.value = designer.renderMetadata
  }

  const off = designer.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

  return {
    designer,
    ready,
    degraded,
    readonly,
    busy,
    phase,
    layout,
    fields,
    selected,
    dirty,
    errorMessage,
    fieldError,
    validation,
    unknownFields,
    duplicateFields,
    renderMetadata,
    setReady: (value) => run(() => designer.setReady(value)),
    setFormCode: (formCode) => run(() => designer.setFormCode(formCode)),
    setLevel: (level, roleId) => run(() => designer.setLevel(level, roleId)),
    setFields: (value) => run(() => designer.setFields(value)),
    setLayouts: (levels) => run(() => designer.setLayouts(levels)),
    setJobs: (jobs) => run(() => designer.setJobs(jobs)),
    select: (target) => run(() => designer.select(target)),
    addField: (fieldKey, sectionKey) => run(() => designer.addField(fieldKey, sectionKey)),
    moveField: (input) => run(() => designer.moveField(input)),
    removeField: (fieldKey) => run(() => designer.removeField(fieldKey)),
    toggleColSpan: (fieldKey) => run(() => designer.toggleColSpan(fieldKey)),
    setColumns: (sectionKey, columns) => run(() => designer.setColumns(sectionKey, columns)),
    addSection: () => run(() => designer.addSection()),
    removeSection: (sectionKey) => run(() => designer.removeSection(sectionKey)),
    renameSection: (sectionKey, title) => run(() => designer.renameSection(sectionKey, title)),
    setLabelPosition: (position) => run(() => designer.setLabelPosition(position)),
    setLabelWidth: (width) => run(() => designer.setLabelWidth(width)),
    setQueryFields: (keys) => run(() => designer.setQueryFields(keys)),
    setDetailColumns: (columns) => run(() => designer.setDetailColumns(columns)),
    markBaseline: () => run(() => designer.markBaseline()),
    discard: () => run(() => designer.discard()),
    needsBlock: (action) => designer.needsBlock(action),
    load: async () => {
      const value = await designer.load()
      sync()
      return value
    },
    save: async () => {
      const value = await designer.save()
      sync()
      return value
    },
    publish: async () => {
      const value = await designer.publish()
      sync()
      return value
    },
    restoreDefault: async () => {
      const value = await designer.restoreDefault()
      sync()
      return value
    },
    createField: async (draft) => {
      const value = await designer.createField(draft)
      sync()
      return value
    },
    retryField: async (fieldKey) => {
      const value = await designer.retryField(fieldKey)
      sync()
      return value
    },
  }
}
