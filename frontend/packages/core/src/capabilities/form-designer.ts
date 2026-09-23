/**
 * 表单设计器能力基类：布局编排（结构操作 / 三级层级 / 脏基线 / 保存发布恢复 / 自建字段）。
 *
 * 组合拖拽能力（`BaseDragDrop`）与表单元数据能力（`BaseFormMeta`）；处理函数由宿主注入，
 * **未注入即占位**（不发请求、返回 `undefined` / `false`）；判定全部经领域纯函数 `domain/form-layout`。
 */

import { BasePlaceholderState } from './placeholder-state'
import { BaseAccess } from './access'
import { BaseDragDrop } from './drag-drop'
import { BaseFormMeta } from './form-meta'
import { BaseNotice } from './notice'

import {
  DEFAULT_LAYOUT_COLUMNS,
  FORMDESIGN_PERM,
  addSection as addSectionIn,
  canDragField,
  checkExtField,
  emptyLayout,
  findDisabledFields,
  findDuplicateFields,
  findUnknownFields,
  hasField as hasFieldIn,
  insertField as insertFieldIn,
  isLayoutDirty,
  moveField as moveFieldIn,
  normalizeLayout,
  normalizeSelection,
  removeField as removeFieldIn,
  removeSection as removeSectionIn,
  renameSection as renameSectionIn,
  resolveEffectiveLayout,
  resolveLayoutForLevel,
  resolveRestoreTarget,
  setDetailColumns as setDetailColumnsIn,
  setLabelPosition as setLabelPositionIn,
  setLabelWidth as setLabelWidthIn,
  setQueryFields as setQueryFieldsIn,
  setSectionColumns as setSectionColumnsIn,
  toRenderMetadata,
  toggleColSpan as toggleColSpanIn,
  validateLayout,
  type DesignerSelection,
  type DesignerLevel,
  type ExtDdlStatus,
  type ExtFieldCheck,
  type ExtFieldDraft,
  type FormField,
  type FormLayout,
  type FormLayoutLevels,
  type LayoutDetailColumnInput,
  type LayoutLabelPosition,
  type LayoutEffective,
  type LayoutValidationResult,
} from '../domain/form-layout'

/** 设计阶段。 */
export type DesignerPhase = 'idle' | 'loading' | 'saving' | 'publishing' | 'restoring' | 'done' | 'failed'

/** 拖拽落点输入（件层由 Sortable 事件适配）。 */
export interface DesignerDropInput {
  /** 字段键。 */
  fieldKey: string
  /** 目标分区键。 */
  toSectionKey?: string
  /** 目标索引。 */
  index?: number
  /** 来源分区键。 */
  fromSectionKey?: string
  /** 是否跨分区。 */
  crossZone?: boolean
}

/** 取数快照。 */
export interface DesignerSnapshot {
  /** 三级层级布局。 */
  levels?: FormLayoutLevels
  /** 合并字段清单。 */
  fields?: readonly FormField[]
}

/** 保存结果。 */
export interface DesignerSaveResult {
  /** 记录版本（乐观锁）。 */
  recordVersion?: number
}

/** 自建字段创建结果。 */
export interface DesignerExtFieldResult {
  /** 字段键。 */
  fieldKey: string
  /** 物理列名。 */
  columnName: string
  /** DDL 状态。 */
  ddlStatus: ExtDdlStatus
}

/** 注入的处理函数集（未注入项按占位：不请求、恒定返回）。 */
export interface DesignerJobs {
  /** 取数（三级层级布局 + 字段清单）。 */
  load?: (input: { formCode: string; level: DesignerLevel; roleId?: string }) => Promise<DesignerSnapshot | undefined>
  /** 保存某层级布局（覆盖式）。 */
  save?: (input: {
    formCode: string
    level: DesignerLevel
    roleId?: string
    layout: FormLayout
  }) => Promise<DesignerSaveResult | undefined>
  /** 发布（触发 `sys.form.updated`）。 */
  publish?: (input: { formCode: string; level: DesignerLevel; roleId?: string }) => Promise<void>
  /** 恢复默认（删除当前层级配置）。 */
  restore?: (input: { formCode: string; level: DesignerLevel; roleId?: string }) => Promise<void>
  /** 新建自建字段（触发 DDL）。 */
  createField?: (input: { formCode: string; draft: ExtFieldDraft }) => Promise<DesignerExtFieldResult | undefined>
  /** DDL 失败重试。 */
  retryField?: (input: { formCode: string; fieldKey: string }) => Promise<DesignerExtFieldResult | undefined>
}

/** 脏数据拦截场景。 */
export type DesignerBlockAction = 'switch-form' | 'switch-level' | 'leave'

/** 表单设计器能力基类（抽象）。 */
export abstract class BaseFormDesigner extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'form-designer'
  /** 依赖能力键（拖拽 / 表单元数据 / 权限 / 提示）。 */
  override readonly depends = ['placeholder-state', 'drag-drop', 'form-meta', 'access', 'notice']
  /** 表单标识。 */
  formCode = ''
  /** 当前层级。 */
  level: DesignerLevel = 'tenant'
  /** 角色标识（角色视图）。 */
  roleId = ''
  /** 数据通路是否就绪。 */
  ready = false
  /** 合并字段清单。 */
  fields: FormField[] = []
  /** 三级层级布局。 */
  levels: FormLayoutLevels = {}
  /** 当前工作布局。 */
  layout: FormLayout = emptyLayout()
  /** 脏基线（未记基线时为 `undefined`）。 */
  baseline: FormLayout | undefined
  /** 画布选中对象。 */
  selected: DesignerSelection | null = null
  /** 当前阶段。 */
  phase: DesignerPhase = 'idle'
  /** 失败文案。 */
  errorMessage = ''
  /** 自建字段校验失败文案。 */
  fieldError = ''
  /** 注入的处理函数集。 */
  jobs: DesignerJobs = {}
  /** 权限上下文。 */
  access: BaseAccess | undefined
  /** 提示通知协作者。 */
  notice: BaseNotice | undefined
  /** 表单元数据能力（组合；未注入即跳过）。 */
  formMeta: BaseFormMeta | undefined
  /** 拖拽能力（组合；未注入仍完成落点）。 */
  drag: BaseDragDrop | undefined
  /** 已注册字段类型（空数组视为不限类型）。 */
  registeredTypes: readonly string[] = []


  /** 层级是否只读（平台默认层级恒只读）。 */
  get levelReadonly(): boolean {
    return this.level === 'platform'
  }

  /** 是否只读（占位 / 层级只读 / 无维护权限）。 */
  get readonly(): boolean {
    return this.degraded || this.levelReadonly || !this.hasManage()
  }

  /** 是否可编辑。 */
  get canEdit(): boolean {
    return !this.readonly
  }

  /** 是否进行中。 */
  get busy(): boolean {
    return (
      this.phase === 'loading' || this.phase === 'saving' || this.phase === 'publishing' || this.phase === 'restoring'
    )
  }

  /** 是否可保存（就绪 ∧ 可编辑 ∧ 校验通过 ∧ 非进行中）。 */
  get canSave(): boolean {
    return !this.readonly && !this.busy && this.validation.valid
  }

  /** 是否脏（当前布局与基线比对）。 */
  get dirty(): boolean {
    return isLayoutDirty(this.layout, this.baseline)
  }

  /** 布局校验结果。 */
  get validation(): LayoutValidationResult {
    return validateLayout(this.layout, this.fields)
  }

  /** 失效字段引用（清单中不存在）。 */
  get unknownFields(): string[] {
    return findUnknownFields(this.layout, this.fields)
  }

  /** 停用 / 建列失败字段引用。 */
  get disabledFields(): string[] {
    return findDisabledFields(this.layout, this.fields)
  }

  /** 重复引用字段。 */
  get duplicateFields(): string[] {
    return findDuplicateFields(this.layout)
  }

  /** 生效布局（按**已存层级**解析，含空布局回退与只读判定）。 */
  get effective(): LayoutEffective {
    return resolveEffectiveLayout({
      levels: this.levels,
      level: this.level,
      fields: this.fields,
      hasManage: this.hasManage(),
    })
  }

  /** 渲染输入（与设计器产出同形；供渲染器与画布预览复用）。 */
  get renderMetadata(): LayoutEffective {
    return toRenderMetadata(this.effective)
  }

  /**
   * 是否持维护权限（未注入权限上下文视为有权，后端兜底）。
   */
  protected hasManage(): boolean {
    return this.access === undefined || this.access.has(FORMDESIGN_PERM)
  }


  /**
   * 注入处理函数集（整体替换；未注入的项按占位）。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: DesignerJobs): void {
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
   * 注入拖拽能力。
   *
   * @param drag 拖拽能力。
   */
  setDrag(drag: BaseDragDrop | undefined): void {
    this.drag = drag
    this.notifyLifecycle('update')
  }

  /**
   * 设置已注册字段类型。
   *
   * @param types 类型清单（空数组视为不限）。
   */
  setRegisteredTypes(types: readonly string[]): void {
    this.registeredTypes = [...types]
    this.notifyLifecycle('update')
  }

  /**
   * 切换表单（脏数据时不切换并返回 `false`）。
   *
   * @param formCode 表单标识。
   */
  setFormCode(formCode: string): boolean {
    if (formCode !== this.formCode && !this.canSwitch()) {
      return false
    }
    this.formCode = formCode
    this.selected = null
    this.levels = {}
    this.layout = emptyLayout()
    this.markBaseline()
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 切换层级（脏数据时不切换并返回 `false`）。
   *
   * @param level 层级。
   * @param roleId 角色标识。
   */
  setLevel(level: DesignerLevel, roleId?: string): boolean {
    if (level !== this.level && !this.canSwitch()) {
      return false
    }
    this.level = level
    this.roleId = roleId ?? ''
    this.selected = null
    this.applyLevelLayout()
    this.markBaseline()
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置合并字段清单。
   *
   * @param fields 字段清单。
   */
  setFields(fields: readonly FormField[]): void {
    this.fields = [...fields]
    this.notifyLifecycle('update')
  }

  /**
   * 设置三级层级布局（**装载入口**：整体替换、重取工作副本并重置脏基线，与 `load` 同口径）。
   *
   * @param levels 三级层级布局。
   */
  setLayouts(levels?: FormLayoutLevels): void {
    this.levels = { ...(levels ?? {}) }
    this.applyLevelLayout()
    this.markBaseline()
    this.notifyLifecycle('update')
  }

  /**
   * 设置画布选中对象。
   *
   * @param target 选中对象（`null` 为清空）。
   */
  select(target: DesignerSelection | null): void {
    this.selected = normalizeSelection(target)
    this.notifyLifecycle('update')
  }

  /**
   * 取数（未就绪 / 未注入处理函数时占位不动作）。
   */
  async load(): Promise<DesignerSnapshot | undefined> {
    if (this.degraded || this.jobs.load === undefined || this.busy) {
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
      const snapshot = await this.jobs.load({
        formCode: this.formCode,
        level: this.level,
        roleId: this.roleId || undefined,
      })
      this.levels = { ...(snapshot?.levels ?? {}) }
      if (snapshot?.fields !== undefined) {
        this.fields = [...snapshot.fields]
      }
      this.applyLevelLayout()
      this.markBaseline()
      this.phase = 'done'
      this.notifyLifecycle('update')
      return snapshot
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormDesigner.load' })
      this.notifyLifecycle('update')
      return undefined
    }
  }

  /**
   * 新增字段入画布（重复引用 / 不可拖入 / 只读时不动作）。
   *
   * @param fieldKey 字段键。
   * @param sectionKey 目标分区键（缺省首个分区）。
   */
  addField(fieldKey: string, sectionKey?: string): boolean {
    if (!this.canEdit) {
      return false
    }
    const field = this.fields.find((item) => item.key === fieldKey)
    if (field === undefined || !canDragField(field, this.registeredTypes)) {
      return false
    }
    if (hasFieldIn(this.layout, fieldKey)) {
      return false
    }
    this.layout = insertFieldIn(this.layout, fieldKey, sectionKey)
    this.selected = { kind: 'field', key: fieldKey }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 拖拽落点（新增 / 跨分区 / 分区内排序；经拖拽能力广播）。
   *
   * @param input 落点输入。
   */
  moveField(input: DesignerDropInput): boolean {
    if (!this.canEdit) {
      return false
    }
    const located = hasFieldIn(this.layout, input.fieldKey)
    const crossZone =
      input.crossZone ?? (input.fromSectionKey !== undefined && input.fromSectionKey !== input.toSectionKey)
    if (located) {
      this.layout = moveFieldIn(this.layout, input.fieldKey, input.toSectionKey ?? '', input.index)
    } else {
      this.layout = insertFieldIn(this.layout, input.fieldKey, input.toSectionKey, input.index)
    }
    this.selected = { kind: 'field', key: input.fieldKey }
    this.drag?.emitDrag({
      phase: 'drop',
      source: input.fromSectionKey ?? '',
      target: input.toSectionKey,
      crossZone,
    })
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 移出字段（回字段调板，字段定义不受影响）。
   *
   * @param fieldKey 字段键。
   */
  removeField(fieldKey: string): boolean {
    if (!this.canEdit || !hasFieldIn(this.layout, fieldKey)) {
      return false
    }
    this.layout = removeFieldIn(this.layout, fieldKey)
    if (this.selected?.kind === 'field' && this.selected.key === fieldKey) {
      this.selected = null
    }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 翻转字段跨列。
   *
   * @param fieldKey 字段键。
   */
  toggleColSpan(fieldKey: string): boolean {
    if (!this.canEdit || !hasFieldIn(this.layout, fieldKey)) {
      return false
    }
    this.layout = toggleColSpanIn(this.layout, fieldKey)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置分区列数。
   *
   * @param sectionKey 分区键。
   * @param columns 列数。
   */
  setColumns(sectionKey: string, columns: unknown): boolean {
    if (!this.canEdit) {
      return false
    }
    const next = setSectionColumnsIn(this.layout, sectionKey, columns)
    if (next === this.layout) {
      return false
    }
    this.layout = next
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 新增分区（返回新分区键；只读时返回空串）。
   */
  addSection(): string {
    if (!this.canEdit) {
      return ''
    }
    const { layout, key } = addSectionIn(this.layout, undefined, '', DEFAULT_LAYOUT_COLUMNS)
    if (key === '') {
      return ''
    }
    this.layout = layout
    this.selected = { kind: 'section', key }
    this.notifyLifecycle('update')
    return key
  }

  /**
   * 删除分区（连同字段引用）。
   *
   * @param sectionKey 分区键。
   */
  removeSection(sectionKey: string): boolean {
    if (!this.canEdit) {
      return false
    }
    const next = removeSectionIn(this.layout, sectionKey)
    if (next === this.layout) {
      return false
    }
    this.layout = next
    if (this.selected?.kind === 'section' && this.selected.key === sectionKey) {
      this.selected = null
    }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 重命名分区。
   *
   * @param sectionKey 分区键。
   * @param title 标题。
   */
  renameSection(sectionKey: string, title: string): boolean {
    if (!this.canEdit) {
      return false
    }
    const next = renameSectionIn(this.layout, sectionKey, title)
    if (next === this.layout) {
      return false
    }
    this.layout = next
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置标签位置。
   *
   * @param position 标签位置。
   */
  setLabelPosition(position: LayoutLabelPosition): boolean {
    if (!this.canEdit) {
      return false
    }
    this.layout = setLabelPositionIn(this.layout, position)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置标签宽度（夹取到 0 ~ 400 整数）。
   *
   * @param width 宽度。
   */
  setLabelWidth(width: unknown): boolean {
    if (!this.canEdit) {
      return false
    }
    this.layout = setLabelWidthIn(this.layout, width)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置查询区字段。
   *
   * @param keys 字段键列表。
   */
  setQueryFields(keys: readonly (string | number)[]): boolean {
    if (!this.canEdit) {
      return false
    }
    this.layout = setQueryFieldsIn(this.layout, keys)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置明细列。
   *
   * @param columns 列列表。
   */
  setDetailColumns(columns: readonly LayoutDetailColumnInput[]): boolean {
    if (!this.canEdit) {
      return false
    }
    this.layout = setDetailColumnsIn(this.layout, columns)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 记脏基线（打开 / 切换层级 / 保存成功后调用）。
   */
  markBaseline(): void {
    this.baseline = normalizeLayout(this.layout)
    this.notifyLifecycle('update')
  }

  /**
   * 撤销未保存变更（回滚到基线；返回是否发生回滚）。
   */
  discard(): boolean {
    if (this.baseline === undefined || !this.dirty) {
      return false
    }
    this.layout = normalizeLayout(this.baseline)
    this.selected = null
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 是否需要拦截（脏数据时为真；件层据此上抛 `dirty-block`）。
   *
   * @param action 拦截场景。
   */
  needsBlock(action: DesignerBlockAction): boolean {
    return action !== undefined && this.dirty
  }

  /**
   * 保存（未注入处理函数时占位不动作；成功后清脏）。
   */
  async save(): Promise<DesignerSaveResult | undefined> {
    if (!this.canSave || this.jobs.save === undefined) {
      return undefined
    }
    this.phase = 'saving'
    this.errorMessage = ''
    this.requestCount += 1
    this.notifyLifecycle('update')
    try {
      const result = await this.jobs.save({
        formCode: this.formCode,
        level: this.level,
        roleId: this.roleId || undefined,
        layout: normalizeLayout(this.layout),
      })
      this.levels = { ...this.levels, [this.level]: normalizeLayout(this.layout) }
      this.markBaseline()
      this.phase = 'done'
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormDesigner.save' })
      this.notifyLifecycle('update')
      return undefined
    }
  }

  /**
   * 发布（触发 `sys.form.updated`；未注入不动作）。
   */
  async publish(): Promise<boolean> {
    if (this.readonly || this.busy || this.jobs.publish === undefined) {
      return false
    }
    this.phase = 'publishing'
    this.requestCount += 1
    this.notifyLifecycle('update')
    try {
      await this.jobs.publish({ formCode: this.formCode, level: this.level, roleId: this.roleId || undefined })
      this.phase = 'done'
      this.notifyLifecycle('update')
      return true
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormDesigner.publish' })
      this.notifyLifecycle('update')
      return false
    }
  }

  /**
   * 恢复默认（删除当前层级配置并按目标逐级回退；未注入不动作）。
   */
  async restoreDefault(): Promise<boolean> {
    if (this.readonly || this.busy || this.jobs.restore === undefined) {
      return false
    }
    this.phase = 'restoring'
    this.requestCount += 1
    this.notifyLifecycle('update')
    try {
      await this.jobs.restore({ formCode: this.formCode, level: this.level, roleId: this.roleId || undefined })
      const target = resolveRestoreTarget(this.level)
      const levels = { ...this.levels }
      delete levels[target.level]
      this.levels = levels
      this.applyLevelLayout()
      this.markBaseline()
      this.phase = 'done'
      this.notifyLifecycle('update')
      return true
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormDesigner.restoreDefault' })
      this.notifyLifecycle('update')
      return false
    }
  }

  /**
   * 新建自建字段（前置校验不通过不请求）。
   *
   * @param draft 草稿。
   */
  async createField(draft: ExtFieldDraft): Promise<DesignerExtFieldResult | undefined> {
    if (this.readonly || this.busy) {
      return undefined
    }
    const check: ExtFieldCheck = checkExtField(
      draft,
      this.fields.map((field) => field.key),
    )
    if (!check.valid) {
      this.fieldError = check.message
      this.notifyLifecycle('update')
      return undefined
    }
    if (this.jobs.createField === undefined) {
      this.fieldError = ''
      this.notifyLifecycle('update')
      return undefined
    }
    this.fieldError = ''
    this.phase = 'saving'
    this.requestCount += 1
    this.notifyLifecycle('update')
    try {
      const result = await this.jobs.createField({ formCode: this.formCode, draft })
      if (result !== undefined) {
        this.fields = [
          ...this.fields,
          { key: result.fieldKey, label: draft.name, type: draft.type, group: 'tenant', status: result.ddlStatus },
        ]
      }
      this.phase = 'done'
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormDesigner.createField' })
      this.notifyLifecycle('update')
      return undefined
    }
  }

  /**
   * DDL 建列失败重试（仅对失败字段动作）。
   *
   * @param fieldKey 字段键。
   */
  async retryField(fieldKey: string): Promise<DesignerExtFieldResult | undefined> {
    if (this.readonly || this.busy) {
      return undefined
    }
    const field = this.fields.find((item) => item.key === fieldKey)
    if (field === undefined || field.status !== 'failed' || this.jobs.retryField === undefined) {
      return undefined
    }
    this.phase = 'saving'
    this.requestCount += 1
    this.notifyLifecycle('update')
    try {
      const result = await this.jobs.retryField({ formCode: this.formCode, fieldKey })
      if (result !== undefined) {
        this.fields = this.fields.map((item) => (item.key === fieldKey ? { ...item, status: result.ddlStatus } : item))
      }
      this.phase = 'done'
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.reportError(error, { scope: 'BaseFormDesigner.retryField' })
      this.notifyLifecycle('update')
      return undefined
    }
  }

  /** 是否允许切换（脏数据拦截）。 */
  private canSwitch(): boolean {
    return !this.dirty
  }

  /** 按当前层级取工作布局（命中层级缺失即空布局回退）。 */
  private applyLevelLayout(): void {
    const resolved = resolveLayoutForLevel(this.levels, this.level)
    this.layout = resolved.layout ?? emptyLayout()
  }
}
