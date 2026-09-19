/**
 * 表单布局元数据契约与设计器编排契约（`@bms/core/testing`）。
 *
 * 设计器 / 渲染器 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言。
 */

import { describe, expect, it } from 'vitest'

import {
  layoutEqual,
  toRenderMetadata,
  type FormField,
  type FormLayout,
  type FormLayoutLevels,
  type LayoutDetailColumnInput,
  type LayoutEffective,
  type LayoutValidationResult,
} from '../src'

/** 契约基（与 `describeContract` 同口径，避免重复实现）。 */
export type FormLayoutContractDefine = () => void

/** 拖拽落点输入（结构化最小面）。 */
export interface FormDesignerDropInput {
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

/** 层级键（结构化最小面，与核心 `DesignerLevel` 同值域）。 */
export type FormDesignerLevel = 'platform' | 'tenant' | 'role'

/** 画布选中项（结构化最小面）。 */
export interface FormDesignerSelection {
  /** 对象类型。 */
  kind: 'field' | 'section'
  /** 对象键。 */
  key: string
}

/** 自建字段草稿（结构化最小面）。 */
export interface FormDesignerExtDraft {
  /** 名称。 */
  name: string
  /** 英文名。 */
  nameEn?: string
  /** 类型。 */
  type: string
  /** 选项集。 */
  options?: readonly { value: string; label: string }[]
}

/** 保存结果（结构化最小面）。 */
export interface FormDesignerSaveResult {
  /** 记录版本。 */
  recordVersion?: number
}

/** 自建字段创建结果（结构化最小面）。 */
export interface FormDesignerExtResult {
  /** 字段键。 */
  fieldKey: string
  /** 物理列名。 */
  columnName: string
  /** DDL 状态。 */
  ddlStatus: 'pending' | 'active' | 'failed'
}

/** 取数快照（结构化最小面）。 */
export interface FormDesignerSnapshot {
  /** 三级层级布局。 */
  levels?: FormLayoutLevels
  /** 字段清单。 */
  fields?: readonly FormField[]
}

/** 处理函数集（结构化最小面；未注入项按占位）。 */
export interface FormDesignerJobs {
  /** 取数。 */
  load?: (input: {
    formCode: string
    level: FormDesignerLevel
    roleId?: string
  }) => Promise<FormDesignerSnapshot | undefined>
  /** 保存。 */
  save?: (input: {
    formCode: string
    level: FormDesignerLevel
    roleId?: string
    layout: FormLayout
  }) => Promise<FormDesignerSaveResult | undefined>
  /** 发布。 */
  publish?: (input: { formCode: string; level: FormDesignerLevel; roleId?: string }) => Promise<void>
  /** 恢复默认。 */
  restore?: (input: { formCode: string; level: FormDesignerLevel; roleId?: string }) => Promise<void>
  /** 新建自建字段。 */
  createField?: (input: { formCode: string; draft: FormDesignerExtDraft }) => Promise<FormDesignerExtResult | undefined>
  /** DDL 重试。 */
  retryField?: (input: { formCode: string; fieldKey: string }) => Promise<FormDesignerExtResult | undefined>
}

/** 元数据契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface FormLayoutContractTarget {
  /** 当前工作布局。 */
  readonly layout: FormLayout
  /** 三级层级布局。 */
  readonly levels: FormLayoutLevels
  /** 字段清单。 */
  readonly fields: readonly FormField[]
  /** 当前层级。 */
  readonly level: FormDesignerLevel
  /** 是否只读。 */
  readonly readonly: boolean
  /** 是否脏。 */
  readonly dirty: boolean
  /** 生效布局。 */
  effective(): LayoutEffective
  /** 渲染输入。 */
  renderMetadata(): LayoutEffective
  /** 校验结果。 */
  validation(): LayoutValidationResult
  /** 失效字段引用。 */
  unknownFields(): string[]
  /** 重复引用字段。 */
  duplicateFields(): string[]
  /** 设置三级层级布局。 */
  setLayouts(levels?: FormLayoutLevels): void
  /** 设置字段清单。 */
  setFields(fields: readonly FormField[]): void
  /** 切换层级。 */
  setLevel(level: FormDesignerLevel): void
  /** 新增字段。 */
  addField(fieldKey: string, sectionKey?: string): boolean
  /** 拖拽落点。 */
  moveField(input: FormDesignerDropInput): boolean
  /** 移出字段。 */
  removeField(fieldKey: string): boolean
  /** 翻转跨列。 */
  toggleColSpan(fieldKey: string): boolean
  /** 设置分区列数。 */
  setColumns(sectionKey: string, columns: unknown): boolean
  /** 新增分区（返回新分区键）。 */
  addSection(): string
  /** 删除分区。 */
  removeSection(sectionKey: string): boolean
  /** 重命名分区。 */
  renameSection(sectionKey: string, title: string): boolean
  /** 设置标签位置。 */
  setLabelPosition(position: 'top' | 'left'): boolean
  /** 设置标签宽度。 */
  setLabelWidth(width: unknown): boolean
  /** 设置查询区字段。 */
  setQueryFields(keys: readonly (string | number)[]): boolean
  /** 设置明细列。 */
  setDetailColumns(columns: readonly LayoutDetailColumnInput[]): boolean
  /** 记基线。 */
  markBaseline(): void
  /** 撤销未保存变更。 */
  discard(): boolean
}

/** 设计器编排契约面（结构化）。 */
export interface FormDesignerContractTarget {
  /** 是否就绪。 */
  readonly ready: boolean
  /** 是否降级。 */
  readonly degraded: boolean
  /** 是否只读。 */
  readonly readonly: boolean
  /** 是否可编辑。 */
  readonly canEdit: boolean
  /** 是否可保存。 */
  readonly canSave: boolean
  /** 是否进行中。 */
  readonly busy: boolean
  /** 请求计数。 */
  readonly requestCount: number
  /** 阶段。 */
  readonly phase: string
  /** 当前布局。 */
  layout(): FormLayout
  /** 字段清单。 */
  fields(): readonly FormField[]
  /** 选中对象。 */
  selected(): FormDesignerSelection | null
  /** 是否脏。 */
  dirty(): boolean
  /** 校验结果。 */
  validation(): LayoutValidationResult
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入处理函数集。 */
  setJobs(jobs: FormDesignerJobs): void
  /** 注入权限码与已注册类型。 */
  setOperators(input: { codes?: readonly string[]; registeredTypes?: readonly string[] }): void
  /** 取数。 */
  load(): Promise<unknown>
  /** 选中。 */
  select(target: FormDesignerSelection | null): void
  /** 新增字段。 */
  addField(fieldKey: string, sectionKey?: string): boolean
  /** 拖拽落点。 */
  moveField(input: FormDesignerDropInput): boolean
  /** 设置分区列数。 */
  setColumns(sectionKey: string, columns: unknown): boolean
  /** 新增分区（返回新分区键）。 */
  addSection(): string
  /** 撤销。 */
  discard(): boolean
  /** 是否需拦截。 */
  needsBlock(action: 'switch-form' | 'switch-level' | 'leave'): boolean
  /** 切换表单。 */
  setFormCode(formCode: string): boolean
  /** 切换层级。 */
  setLevel(level: FormDesignerLevel): boolean
  /** 保存。 */
  save(): Promise<FormDesignerSaveResult | undefined>
  /** 发布。 */
  publish(): Promise<boolean>
  /** 恢复默认。 */
  restoreDefault(): Promise<boolean>
  /** 新建自建字段。 */
  createField(draft: FormDesignerExtDraft): Promise<FormDesignerExtResult | undefined>
  /** DDL 重试。 */
  retryField(fieldKey: string): Promise<FormDesignerExtResult | undefined>
}

/** 契约字段清单：平台字段 `name` + 租户自建 `project_no`。 */
export const FORM_CONTRACT_FIELDS: readonly FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active' },
  { key: 'remark', label: '备注', type: 'longtext', group: 'platform', status: 'active' },
  { key: 'project_no', label: '项目编号', type: 'text', group: 'tenant', status: 'active' },
  { key: 'ext_broken', label: '建列失败字段', type: 'text', group: 'tenant', status: 'failed' },
]

/** 契约布局工厂：单分区多字段。 */
export function contractLayout(keys: readonly string[] = ['name']): FormLayout {
  return {
    main: {
      labelPosition: 'top',
      sections: [{ key: 's1', title: '基本信息', columns: 2, fields: keys.map((key) => ({ key })) }],
    },
  }
}

/**
 * 元数据契约（`domain/form-layout` + `BaseFormDesigner` 的布局语义；`08-6-1` 首次落地，`08-6-2` 渲染器复用）。
 *
 * 目标约定：字段清单为 `FORM_CONTRACT_FIELDS`；初始层级 `tenant`、布局 `contractLayout(['name'])`、
 * 已注入维护权限（`formdesign:manage`）与注册类型（含 `text` / `longtext`）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeFormLayoutContract(name: string, create: () => FormLayoutContractTarget): void {
  describe(name, () => {
    it('空布局回退默认栅格（保无配置可用）', () => {
      const target = create()
      target.setLayouts({})
      target.setFields(FORM_CONTRACT_FIELDS)
      const effective = target.effective()
      expect(effective.fallback).toBe(true)
      expect(effective.source).toBe('empty')
      expect(effective.layout.main.sections).toHaveLength(1)
      expect(effective.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual([
        'name',
        'remark',
        'project_no',
      ])
    })

    it('三级层级解析与逐级回退（角色 → 租户 → 平台 → 空布局）', () => {
      const target = create()
      target.setFields(FORM_CONTRACT_FIELDS)
      target.setLayouts({ platform: contractLayout(['name']), tenant: contractLayout(['name', 'remark']) })

      target.setLevel('role')
      expect(target.effective().source).toBe('tenant')
      expect(target.effective().layout.main.sections[0]?.fields).toHaveLength(2)

      target.setLevel('tenant')
      expect(target.effective().source).toBe('tenant')

      target.setLayouts({ platform: contractLayout(['name']) })
      target.setLevel('tenant')
      expect(target.effective().source).toBe('platform')

      target.setLayouts({})
      expect(target.effective().source).toBe('empty')
    })

    it('平台默认层级只读', () => {
      const target = create()
      target.setFields(FORM_CONTRACT_FIELDS)
      target.setLayouts({ platform: contractLayout(['name']) })
      target.setLevel('tenant')
      expect(target.readonly).toBe(false)

      target.setLevel('platform')
      expect(target.readonly).toBe(true)
    })

    it('结构操作：插入幂等、跨分区移动、删分区连带引用', () => {
      const target = create()
      target.setLayouts({ tenant: contractLayout(['name']) })
      target.setLevel('tenant')
      target.markBaseline()

      expect(target.addField('name')).toBe(false)
      expect(target.addField('remark')).toBe(true)
      expect(target.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])

      const sectionKey = target.addSection()
      expect(sectionKey).not.toBe('')
      expect(target.moveField({ fieldKey: 'remark', toSectionKey: sectionKey })).toBe(true)
      const sections = target.layout.main.sections
      expect(sections[0]?.fields.map((field) => field.key)).toEqual(['name'])
      expect(sections[1]?.fields.map((field) => field.key)).toEqual(['remark'])

      expect(target.removeSection(sectionKey)).toBe(true)
      expect(target.layout.main.sections).toHaveLength(1)
      expect(target.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name'])
    })

    it('分区内排序按移出后索引落位', () => {
      const target = create()
      target.setLayouts({ tenant: contractLayout(['name', 'remark', 'project_no']) })
      target.setLevel('tenant')
      target.markBaseline()

      expect(target.moveField({ fieldKey: 'name', toSectionKey: 's1', index: 2 })).toBe(true)
      expect(target.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['remark', 'project_no', 'name'])
    })

    it('跨列翻转、列数夹取、标签宽度夹取', () => {
      const target = create()
      target.setLayouts({ tenant: contractLayout(['name', 'remark']) })
      target.setLevel('tenant')
      target.markBaseline()

      expect(target.toggleColSpan('name')).toBe(true)
      expect(target.layout.main.sections[0]?.fields[0]?.colSpan).toBe(true)
      expect(target.toggleColSpan('name')).toBe(true)
      expect(target.layout.main.sections[0]?.fields[0]?.colSpan).toBeUndefined()

      expect(target.setColumns('s1', 9)).toBe(true)
      expect(target.layout.main.sections[0]?.columns).toBe(3)
      expect(target.setColumns('s1', 1)).toBe(true)
      expect(target.layout.main.sections[0]?.columns).toBe(1)
      expect(target.setColumns('absent', 2)).toBe(false)

      expect(target.setLabelWidth(9999)).toBe(true)
      expect(target.layout.main.labelWidth).toBe(400)
      expect(target.setLabelPosition('left')).toBe(true)
      expect(target.layout.main.labelPosition).toBe('left')
    })

    it('查询区与明细区归一（去重保序、宽度夹取）', () => {
      const target = create()
      target.setLayouts({ tenant: contractLayout(['name']) })
      target.setLevel('tenant')
      target.markBaseline()

      expect(target.setQueryFields(['name', 'name', 'remark'])).toBe(true)
      expect(target.layout.query?.fields).toEqual(['name', 'remark'])

      expect(target.setDetailColumns([{ key: 'project_no', width: 9999 }, 'project_no', 'name'])).toBe(true)
      expect(target.layout.detail?.columns).toEqual([{ key: 'project_no', width: 800 }, { key: 'name' }])

      expect(target.setQueryFields([])).toBe(true)
      expect(target.layout.query).toBeUndefined()
    })

    it('失效与重复引用可识别且不阻断', () => {
      const target = create()
      target.setFields(FORM_CONTRACT_FIELDS)
      target.setLayouts({ tenant: contractLayout(['name', 'absent_key']) })
      target.setLevel('tenant')
      expect(target.unknownFields()).toEqual(['absent_key'])
      expect(target.duplicateFields()).toEqual([])

      target.setLayouts({
        tenant: {
          main: {
            labelPosition: 'top',
            sections: [
              { key: 's1', title: '', columns: 2, fields: [{ key: 'name' }] },
              { key: 's2', title: '', columns: 2, fields: [{ key: 'name' }] },
            ],
          },
        },
      })
      target.setLevel('tenant')
      expect(target.duplicateFields()).toEqual(['name'])
    })

    it('校验：引用失效 / 停用 / 重复 / 空分区逐项入错', () => {
      const target = create()
      target.setFields(FORM_CONTRACT_FIELDS)
      target.setLayouts({ tenant: contractLayout(['name']) })
      target.setLevel('tenant')
      target.markBaseline()
      expect(target.validation().valid).toBe(true)

      target.setLayouts({ tenant: contractLayout(['name', 'ext_broken']) })
      target.setLevel('tenant')
      expect(target.validation().valid).toBe(false)
      expect(target.validation().errors.map((issue) => issue.kind)).toContain('disabled-field')

      const sectionKey = target.addSection()
      expect(
        target.validation().errors.some((issue) => issue.kind === 'empty-section' && issue.sectionKey === sectionKey),
      ).toBe(true)
    })

    it('脏基线：改动置脏、撤销回不脏、键序无关', () => {
      const target = create()
      target.setLayouts({ tenant: contractLayout(['name']) })
      target.setLevel('tenant')
      target.markBaseline()
      expect(target.dirty).toBe(false)

      target.addField('remark')
      expect(target.dirty).toBe(true)
      expect(target.discard()).toBe(true)
      expect(target.dirty).toBe(false)
      expect(target.discard()).toBe(false)

      target.setLayouts({
        tenant: {
          main: {
            labelPosition: 'top',
            sections: [{ key: 's1', title: '基本信息', columns: 2, fields: [{ key: 'name', colSpan: false }] }],
          },
        },
      })
      target.setLevel('tenant')
      target.markBaseline()
      expect(target.dirty).toBe(false)
    })

    it('渲染输入与设计产出同形（设计 → 渲染一致）', () => {
      const target = create()
      target.setFields(FORM_CONTRACT_FIELDS)
      target.setLayouts({ tenant: contractLayout(['name', 'remark']) })
      target.setLevel('tenant')
      target.markBaseline()

      expect(layoutEqual(target.renderMetadata().layout, target.layout)).toBe(true)
      expect(target.renderMetadata()).toEqual(toRenderMetadata(target.effective()))
      expect(target.renderMetadata().fields.map((field) => field.key)).toEqual([
        'name',
        'remark',
        'project_no',
        'ext_broken',
      ])
    })
  })
}

/**
 * 设计器编排契约（`BaseFormDesigner`；`08-6-1` 首次落地）。
 *
 * 目标约定：表单 `leave`、层级 `tenant`、初始未注入处理函数与权限上下文（按有权）；
 * 取数返回两级层布局（`tenant` 一分区一字段 / `platform` 一分区两字段）与 `FORM_CONTRACT_FIELDS`；
 * 保存返回 `{ recordVersion: 3 }`；自建字段返回 `{ fieldKey: 'ext_no', columnName: 'ext_ext_no', ddlStatus: 'pending' }`。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeFormDesignerContract(name: string, create: () => FormDesignerContractTarget): void {
  /** 契约取数快照。 */
  const snapshot: FormDesignerSnapshot = {
    levels: { tenant: contractLayout(['name']), platform: contractLayout(['name', 'remark']) },
    fields: FORM_CONTRACT_FIELDS,
  }
  /** 构造已就绪且已装载的目标。 */
  const loadedTarget = async (jobs: FormDesignerJobs = {}): Promise<FormDesignerContractTarget> => {
    const target = create()
    target.setOperators({ codes: ['formdesign:manage'], registeredTypes: ['text', 'longtext'] })
    target.setJobs({ load: async () => snapshot, ...jobs })
    target.setReady(true)
    await target.load()
    return target
  }

  describe(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      target.setOperators({ codes: ['formdesign:manage'] })
      target.setJobs({ load: async () => snapshot, save: async () => ({ recordVersion: 1 }) })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.readonly).toBe(true)
      await target.load()
      await expect(target.save()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入处理函数时不产生请求（占位）', async () => {
      const target = create()
      target.setOperators({ codes: ['formdesign:manage'] })
      target.setReady(true)
      expect(target.degraded).toBe(false)
      await target.load()
      await expect(target.save()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('取数装载层级与字段并记基线（初始不脏）', async () => {
      const target = await loadedTarget()
      expect(target.requestCount).toBe(1)
      expect(target.phase).toBe('done')
      expect(target.fields().map((field) => field.key)).toContain('name')
      expect(target.layout().main.sections[0]?.fields.map((field) => field.key)).toEqual(['name'])
      expect(target.dirty()).toBe(false)
      expect(target.canSave).toBe(true)
      expect(target.canEdit).toBe(true)
    })

    it('只读（平台默认层级）下结构操作不动作且不写脏', async () => {
      const target = await loadedTarget()
      expect(target.setLevel('platform')).toBe(true)
      expect(target.readonly).toBe(true)
      expect(target.canEdit).toBe(false)
      expect(target.addField('project_no')).toBe(false)
      expect(target.setColumns('s1', 3)).toBe(false)
      expect(target.dirty()).toBe(false)
    })

    it('无维护权限时只读且不可编辑', async () => {
      const target = await loadedTarget()
      target.setOperators({ codes: [], registeredTypes: ['text', 'longtext'] })
      expect(target.readonly).toBe(true)
      expect(target.addField('remark')).toBe(false)
      expect(target.dirty()).toBe(false)

      target.setOperators({ codes: ['formdesign:manage'], registeredTypes: ['text', 'longtext'] })
      expect(target.canEdit).toBe(true)
      expect(target.addField('remark')).toBe(true)
    })

    it('拖拽落点：新增 / 跨分区 / 重复拖入拒绝', async () => {
      const target = await loadedTarget()
      expect(target.addField('name')).toBe(false)
      expect(target.addField('remark')).toBe(true)
      expect(target.selected()).toEqual({ kind: 'field', key: 'remark' })

      const sectionKey = target.addSection()
      expect(sectionKey).not.toBe('')
      expect(
        target.moveField({ fieldKey: 'remark', toSectionKey: sectionKey, fromSectionKey: 's1', crossZone: true }),
      ).toBe(true)
      const sections = target.layout().main.sections
      expect(sections[0]?.fields.map((field) => field.key)).toEqual(['name'])
      expect(sections[1]?.fields.map((field) => field.key)).toEqual(['remark'])
    })

    it('脏判定与拦截（切换表单 / 切换层级）', async () => {
      const target = await loadedTarget()
      expect(target.needsBlock('leave')).toBe(false)
      expect(target.setFormCode('user')).toBe(true)

      target.addField('remark')
      expect(target.dirty()).toBe(true)
      expect(target.needsBlock('leave')).toBe(true)
      expect(target.needsBlock('switch-level')).toBe(true)
      expect(target.setFormCode('other')).toBe(false)
      expect(target.setLevel('role')).toBe(false)

      expect(target.discard()).toBe(true)
      expect(target.needsBlock('leave')).toBe(false)
      expect(target.setLevel('role')).toBe(true)
    })

    it('保存：成功清脏并写回层级，失败保留本地与脏标记', async () => {
      let fail = true
      const target = await loadedTarget({
        save: async () => {
          if (fail) {
            throw new Error('保存失败')
          }
          return { recordVersion: 3 }
        },
      })
      target.addField('remark')
      await expect(target.save()).resolves.toBeUndefined()
      expect(target.phase).toBe('failed')
      expect(target.dirty()).toBe(true)

      fail = false
      await expect(target.save()).resolves.toEqual({ recordVersion: 3 })
      expect(target.phase).toBe('done')
      expect(target.dirty()).toBe(false)
      expect(target.requestCount).toBe(3)
    })

    it('发布：未注入不动作，注入后可发布', async () => {
      const target = await loadedTarget()
      await expect(target.publish()).resolves.toBe(false)

      const published: string[] = []
      target.setJobs({
        publish: async (input) => {
          published.push(input.formCode)
        },
      })
      await expect(target.publish()).resolves.toBe(true)
      expect(published).toEqual(['leave'])
    })

    it('恢复默认：逐级回退（租户 → 平台）', async () => {
      const restored: string[] = []
      const target = await loadedTarget({
        restore: async (input) => {
          restored.push(input.level)
        },
      })
      await expect(target.restoreDefault()).resolves.toBe(true)
      expect(restored).toEqual(['tenant'])
      expect(target.layout().main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
      expect(target.dirty()).toBe(false)
    })

    it('自建字段：校验不通过不请求，通过后入清单', async () => {
      const target = await loadedTarget({
        createField: async (input) => ({
          fieldKey: input.draft.name,
          columnName: `ext_${input.draft.name}`,
          ddlStatus: 'pending',
        }),
      })
      const before = target.requestCount

      await expect(target.createField({ name: '', type: 'text' })).resolves.toBeUndefined()
      await expect(target.createField({ name: 'no', type: 'richtext' })).resolves.toBeUndefined()
      await expect(target.createField({ name: 'no', type: 'select' })).resolves.toBeUndefined()
      await expect(target.createField({ name: 'name', type: 'text' })).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)

      await expect(target.createField({ name: 'project_no_new', type: 'text' })).resolves.toMatchObject({
        ddlStatus: 'pending',
      })
      expect(target.fields().map((field) => field.key)).toContain('project_no_new')
      expect(target.requestCount).toBe(before + 1)
    })

    it('DDL 重试仅对建列失败字段动作', async () => {
      const target = await loadedTarget({
        retryField: async (input) => ({ fieldKey: input.fieldKey, columnName: 'ext_ext_broken', ddlStatus: 'active' }),
      })
      await expect(target.retryField('name')).resolves.toBeUndefined()
      await expect(target.retryField('ext_broken')).resolves.toMatchObject({ ddlStatus: 'active' })
      expect(target.fields().find((field) => field.key === 'ext_broken')?.status).toBe('active')
    })

    it('进行中重复提交不动作（防重复）', async () => {
      let release: () => void = () => undefined
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const target = await loadedTarget({
        save: async () => {
          await gate
          return { recordVersion: 1 }
        },
      })
      target.addField('remark')
      const pending = target.save()
      expect(target.busy).toBe(true)
      await expect(target.save()).resolves.toBeUndefined()
      release()
      await expect(pending).resolves.toEqual({ recordVersion: 1 })
      expect(target.requestCount).toBe(2)
    })
  })
}
