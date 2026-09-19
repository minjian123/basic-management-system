/**
 * 渲染编排契约（`@bms/core/testing`）。
 *
 * 渲染器为「同一契约多实现」，各端（PC / 移动端）在本套件中传入适配器跑同一套断言。
 */

import { describe, expect, it } from 'vitest'

import { DEFAULT_SECTION_KEY, type FieldPermission, type FormField, type FormLayout } from '../src'

/** 渲染三态（结构化最小面，与核心 `FormRenderMode` 同值域）。 */
export type RenderContractMode = 'create' | 'edit' | 'view'

/** 字段渲染状态（结构化最小面）。 */
export interface RenderContractState {
  /** 是否渲染。 */
  visible: boolean
  /** 是否可编辑。 */
  editable: boolean
  /** 是否禁用。 */
  disabled: boolean
  /** 是否必填。 */
  required: boolean
  /** 是否脱敏。 */
  masked: boolean
  /** 是否只读回显。 */
  displayOnly: boolean
}

/** 字段渲染项（结构化最小面）。 */
export interface RenderContractField extends RenderContractState {
  /** 字段键。 */
  key: string
  /** 字段名。 */
  label: string
  /** 控件语义键。 */
  widget: string
  /** 是否未知类型。 */
  unknown: boolean
  /** 是否跨整行。 */
  colSpan: boolean
  /** 占位提示。 */
  placeholder: string
  /** 选项集值。 */
  options: readonly string[]
  /** 规则种类。 */
  ruleKinds: readonly string[]
  /** 当前值。 */
  value: unknown
}

/** 分组 / 分区渲染项（结构化最小面）。 */
export interface RenderContractSection {
  /** 分区键。 */
  key: string
  /** 列数。 */
  columns: number
  /** 字段。 */
  fields: readonly RenderContractField[]
  /** 分组键集合。 */
  groupKeys: readonly string[]
  /** 首分组的字段键。 */
  firstGroupKeys: readonly string[]
}

/** 明细列渲染项（结构化最小面）。 */
export interface RenderContractDetailColumn {
  /** 列字段键。 */
  key: string
  /** 列标题。 */
  title: string
  /** 是否可编辑。 */
  editable: boolean
}

/** 渲染计划（结构化最小面）。 */
export interface RenderContractPlan {
  /** 分区。 */
  sections: readonly RenderContractSection[]
  /** 明细列。 */
  detailColumns: readonly RenderContractDetailColumn[]
  /** 明细列是否回退。 */
  detailFallback: boolean
  /** 失效字段。 */
  unknownFields: readonly string[]
  /** 停用字段。 */
  disabledFields: readonly string[]
  /** 不可见字段。 */
  hiddenFields: readonly string[]
  /** 是否空布局回退。 */
  fallback: boolean
  /** 是否只读。 */
  readonly: boolean
}

/** 校验结果（结构化最小面）。 */
export interface RenderContractValidation {
  /** 是否通过。 */
  valid: boolean
  /** 错误字段键。 */
  errorFields: readonly string[]
  /** 首个错误字段。 */
  firstField: string | undefined
  /** 汇总文案。 */
  message: string
}

/** 明细校验结果（结构化最小面）。 */
export interface RenderContractDetailValidation {
  /** 是否通过。 */
  valid: boolean
  /** 错误定位（`页签:行:字段`）。 */
  positions: readonly string[]
  /** 汇总文案。 */
  message: string
}

/** 提交载荷（结构化最小面）。 */
export interface RenderContractPayload {
  /** 表单标识。 */
  formCode: string
  /** 三态。 */
  mode: RenderContractMode
  /** 记录主键。 */
  recordId?: string | number
  /** 主表数据。 */
  data: Record<string, unknown>
  /** 明细数据。 */
  details: Record<string, Record<string, unknown>[]>
  /** 记录版本。 */
  recordVersion?: number
}

/** 提交结果（结构化最小面）。 */
export interface RenderContractSubmitResult {
  /** 记录版本。 */
  recordVersion?: number
}

/** 处理函数集（结构化最小面；未注入项按占位）。 */
export interface RenderContractJobs {
  /** 取布局元数据。 */
  loadLayout?: (input: { formCode: string; mode: RenderContractMode; recordId?: string | number }) => Promise<unknown>
  /** 取详情。 */
  loadRecord?: (input: { formCode: string; recordId: string | number }) => Promise<unknown>
  /** 提交。 */
  submit?: (input: RenderContractPayload) => Promise<RenderContractSubmitResult | undefined>
}

/** 渲染编排契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface FormRendererContractTarget {
  /** 是否就绪。 */
  readonly ready: boolean
  /** 是否降级。 */
  readonly degraded: boolean
  /** 是否只读。 */
  readonly readonly: boolean
  /** 是否进行中。 */
  readonly busy: boolean
  /** 请求计数。 */
  readonly requestCount: number
  /** 阶段。 */
  readonly phase: string
  /** 三态。 */
  readonly mode: RenderContractMode
  /** 是否可提交。 */
  readonly canSubmit: boolean
  /** 渲染计划。 */
  plan(): RenderContractPlan
  /** 主表字段项。 */
  fields(): readonly RenderContractField[]
  /** 明细列。 */
  detailColumns(): readonly RenderContractDetailColumn[]
  /** 主表校验结果。 */
  validation(): RenderContractValidation
  /** 明细校验结果。 */
  detailValidation(): RenderContractDetailValidation
  /** 失效字段。 */
  unknownFields(): readonly string[]
  /** 停用字段。 */
  disabledFields(): readonly string[]
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入处理函数集。 */
  setJobs(jobs: RenderContractJobs): void
  /** 注入权限上下文与权限标记。 */
  setOperators(input: { codes?: readonly string[]; permissions?: Readonly<Record<string, FieldPermission>> }): void
  /** 切换三态。 */
  setMode(mode: RenderContractMode): boolean
  /** 装载渲染元数据（布局元数据 + 字段清单 + 权限标记）。 */
  setMeta(input: unknown): void
  /** 设置主表数据。 */
  setData(data: Record<string, unknown> | undefined): void
  /** 设置明细数据。 */
  setDetails(details: Record<string, readonly Record<string, unknown>[]> | undefined): void
  /** 设置件层字段覆盖。 */
  setOverrides(overrides: Readonly<Record<string, Record<string, unknown>>> | undefined): void
  /** 写入字段值。 */
  setFieldValue(fieldKey: string, value: unknown): boolean
  /** 读取字段值。 */
  getFieldValue(fieldKey: string): unknown
  /** 整体替换明细行。 */
  setDetailRows(detailKey: string, rows: readonly unknown[]): boolean
  /** 追加明细行。 */
  addDetailRow(detailKey: string, row?: Record<string, unknown>): boolean
  /** 移除明细行。 */
  removeDetailRow(detailKey: string, index: number): boolean
  /** 读取明细行。 */
  detailRows(detailKey: string): readonly Record<string, unknown>[]
  /** 写入明细单元格。 */
  setDetailCell(detailKey: string, index: number, fieldKey: string, value: unknown): boolean
  /** 全量校验。 */
  validate(): RenderContractValidation
  /** 单字段校验。 */
  validateField(fieldKey: string): string | undefined
  /** 取数。 */
  load(): Promise<unknown>
  /** 提交。 */
  submit(): Promise<RenderContractSubmitResult | undefined>
  /** 重试提交。 */
  retry(): Promise<RenderContractSubmitResult | undefined>
  /** 重置。 */
  reset(): void
}

/** 契约字段清单：覆盖语义键映射与未知回退。 */
export const RENDER_CONTRACT_FIELDS: readonly FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active', required: true },
  {
    key: 'remark',
    label: '备注',
    type: 'longtext',
    group: 'platform',
    status: 'active',
    rules: [{ kind: 'length', min: 2, max: 10, message: '备注长度须为 2 ~ 10' }],
  },
  { key: 'amount', label: '金额', type: 'amount', group: 'platform', status: 'active' },
  {
    key: 'level',
    label: '等级',
    type: 'select',
    group: 'platform',
    status: 'active',
    options: [{ value: 'a', label: '甲' }],
  },
  { key: 'join_at', label: '入职日期', type: 'datetime', group: 'platform', status: 'active' },
  { key: 'mystery', label: '未知字段', type: 'wild_type', group: 'platform', status: 'active' },
  { key: 'broken', label: '建列失败', type: 'text', group: 'tenant', status: 'failed' },
  { key: 'project_no', label: '项目编号', type: 'text', group: 'tenant', status: 'active' },
]

/** 契约布局：两分区（`s1` 两字段含跨列；`s2` 含分组 `g1`） + 明细区。 */
export const RENDER_CONTRACT_LAYOUT: FormLayout = {
  main: {
    labelPosition: 'top',
    sections: [
      {
        key: 's1',
        title: '基本信息',
        columns: 2,
        fields: [{ key: 'name' }, { key: 'remark', colSpan: true }, { key: 'absent_key' }],
      },
      {
        key: 's2',
        title: '扩展信息',
        columns: 3,
        fields: [{ key: 'amount' }, { key: 'mystery' }],
        groups: [{ key: 'g1', title: '组织', fields: [{ key: 'project_no' }, { key: 'broken' }] }],
      },
    ],
  },
  detail: { columns: [{ key: 'project_no', width: 200 }, { key: 'remark' }] },
}

/** 契约权限标记：`name` 在查看态放开、`remark` 不可见。 */
export const RENDER_CONTRACT_PERMISSIONS: Readonly<Record<string, FieldPermission>> = {
  name: { editable: true },
  remark: { visible: false },
}

/**
 * 渲染编排契约（`BaseFormRenderer`；`08-6-2` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：表单 `leave`；初始 `mode='edit'`、未注入处理函数、已注入渲染权限 `formdesign:query`；
 * 装载元数据为 `RENDER_CONTRACT_FIELDS` + `RENDER_CONTRACT_LAYOUT` + `RENDER_CONTRACT_PERMISSIONS`；
 * 详情返回 `{ data: { name: '甲', remark: 'ab' }, details: { lines: [{ project_no: 'P1' }] }, recordVersion: 3 }`；
 * 提交返回 `{ recordVersion: 5 }`。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeFormRendererContract(name: string, create: () => FormRendererContractTarget): void {
  /** 构造已就绪、已装载且处于编辑态的目标。 */
  const loadedTarget = (jobs: RenderContractJobs = {}): FormRendererContractTarget => {
    const target = create()
    target.setOperators({ codes: ['formdesign:query'] })
    target.setJobs(jobs)
    target.setReady(true)
    target.setMode('edit')
    target.setMeta({
      layout: RENDER_CONTRACT_LAYOUT,
      fields: RENDER_CONTRACT_FIELDS,
      level: 'tenant',
      source: 'tenant',
      readonly: false,
      fallback: false,
      permissions: RENDER_CONTRACT_PERMISSIONS,
    })
    return target
  }

  describe(name, () => {
    it('未就绪时降级、只读且不产生请求', async () => {
      const target = create()
      target.setJobs({ loadLayout: async () => undefined, submit: async () => ({ recordVersion: 1 }) })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.readonly).toBe(true)
      await target.load()
      await expect(target.submit()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入处理函数时不产生请求（占位）', async () => {
      const target = create()
      target.setOperators({ codes: ['formdesign:query'] })
      target.setReady(true)
      target.setMeta({
        layout: RENDER_CONTRACT_LAYOUT,
        fields: RENDER_CONTRACT_FIELDS,
        permissions: RENDER_CONTRACT_PERMISSIONS,
      })
      expect(target.degraded).toBe(false)
      await target.load()
      await expect(target.submit()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('字段分发：语义键映射覆盖基础控件与字段类，未知类型回退纯文本', () => {
      const target = loadedTarget()
      const byKey = new Map(target.fields().map((field) => [field.key, field]))
      expect(byKey.get('name')?.widget).toBe('text')
      expect(byKey.get('remark')?.widget).toBe('textarea')
      expect(byKey.get('amount')?.widget).toBe('number')
      expect(byKey.get('project_no')?.widget).toBe('text')

      // 未知类型回退纯文本并打标。
      expect(byKey.get('mystery')?.widget).toBe('plain')
      expect(byKey.get('mystery')?.unknown).toBe(true)
    })

    it('渲染计划：跨列、分组与字段迁移、失效字段跳过、停用字段只读保留', async () => {
      const target = loadedTarget()
      const plan = target.plan()
      expect(plan.sections).toHaveLength(2)
      expect(plan.sections[0]?.columns).toBe(2)
      expect(plan.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
      expect(plan.sections[0]?.fields[1]?.colSpan).toBe(true)
      expect(plan.sections[1]?.groupKeys).toEqual(['g1'])
      expect(plan.sections[1]?.firstGroupKeys).toEqual(['project_no', 'broken'])
      // 分组字段同时迁入 `fields` 便于统一遍历。
      expect(plan.sections[1]?.fields.map((field) => field.key)).toEqual(['amount', 'mystery', 'project_no', 'broken'])
      expect(plan.unknownFields).toEqual(['absent_key'])

      target.setMeta({
        layout: {
          main: {
            labelPosition: 'top',
            sections: [{ key: 's1', title: '', columns: 1, fields: [{ key: 'broken' }] }],
          },
        },
        fields: RENDER_CONTRACT_FIELDS,
      })
      expect(target.disabledFields()).toEqual(['broken'])
      // 停用 / 建列失败字段转只读保留（历史数据可见但不可编辑）。
      expect(target.fields()[0]?.editable).toBe(false)
    })

    it('三态叠加：查看态只读、强制只读覆盖、权限可为终态放宽或收紧', async () => {
      const target = loadedTarget()
      expect(target.setMode('view')).toBe(true)
      expect(target.readonly).toBe(true)
      expect(target.fields().find((field) => field.key === 'amount')?.editable).toBe(false)

      // 权限显式 `editable: true` 在查看态放开（拍板口径：权限为终态、双向覆盖）。
      expect(target.fields().find((field) => field.key === 'name')?.editable).toBe(true)

      expect(target.setMode('edit')).toBe(true)
      expect(target.readonly).toBe(false)
      // 权限 `visible: false` 不渲染。
      expect(target.fields().find((field) => field.key === 'remark')?.visible).toBe(false)
      expect(target.plan().hiddenFields).toContain('remark')
      expect(target.plan().sections[0]?.fields.map((field) => field.key)).toContain('remark')
    })

    it('无渲染权限时只读', async () => {
      const target = loadedTarget()
      target.setOperators({ codes: [] })
      expect(target.readonly).toBe(true)
      expect(target.setFieldValue('name', '乙')).toBe(false)
      expect(target.canSubmit).toBe(false)

      target.setOperators({ codes: ['formdesign:query'] })
      expect(target.setFieldValue('name', '乙')).toBe(true)
    })

    it('取数装载元数据并写入运行态（缺省项补确定值）', async () => {
      const target = create()
      target.setOperators({ codes: ['formdesign:query'] })
      target.setJobs({
        loadLayout: async () => ({
          layout: RENDER_CONTRACT_LAYOUT,
          fields: RENDER_CONTRACT_FIELDS,
          permissions: RENDER_CONTRACT_PERMISSIONS,
        }),
      })
      target.setReady(true)
      await expect(target.load()).resolves.toBeDefined()
      expect(target.requestCount).toBe(1)
      expect(target.fields().length).toBeGreaterThan(0)
      expect(target.plan().fallback).toBe(false)
      expect(target.canSubmit).toBe(true)
    })

    it('空布局回退标记透出', async () => {
      const target = loadedTarget()
      target.setMeta({
        layout: { main: { labelPosition: 'top', sections: [] } },
        fields: RENDER_CONTRACT_FIELDS,
        fallback: true,
      })
      expect(target.plan().fallback).toBe(true)
      expect(target.plan().sections).toHaveLength(0)
    })

    it('明细列：按布局下发；未配置时回退默认列', async () => {
      const target = loadedTarget()
      expect(target.detailColumns().map((column) => column.key)).toEqual(['project_no', 'remark'])
      expect(target.plan().detailFallback).toBe(false)

      target.setMeta({
        layout: {
          main: {
            labelPosition: 'top',
            sections: [
              { key: DEFAULT_SECTION_KEY, title: '', columns: 2, fields: [{ key: 'name' }, { key: 'amount' }] },
            ],
          },
        },
        fields: RENDER_CONTRACT_FIELDS,
      })
      expect(target.plan().detailFallback).toBe(true)
      expect(target.detailColumns().map((column) => column.key)).toEqual(['name', 'amount'])
    })

    it('即时校验（写入即校验）与规则命中', async () => {
      const target = loadedTarget()
      target.setData({})
      expect(target.validateField('name')).toBe('必填')
      expect(target.setFieldValue('name', '甲')).toBe(true)

      // `remark` 权限不可见 → 不校验、不阻塞。
      expect(target.validateField('remark')).toBeUndefined()

      // 放开可见后按长度规则命中。
      target.setOperators({ codes: ['formdesign:query'], permissions: {} })
      target.setFieldValue('remark', 'x')
      expect(target.validateField('remark')).toBe('备注长度须为 2 ~ 10')
      target.setFieldValue('remark', 'abcd')
      expect(target.validateField('remark')).toBeUndefined()
    })

    it('不可见与停用字段不阻塞提交', () => {
      const target = loadedTarget()
      // `name` 必填已满足；`remark` 权限不可见，其长度规则不参与校验。
      target.setData({ name: '甲' })
      const result = target.validate()
      expect(result.valid).toBe(true)
      expect(result.firstField).toBeUndefined()
      expect(result.errorFields).toEqual([])
    })

    it('全量校验定位首个错误字段，未通过不请求提交', async () => {
      const target = loadedTarget({ submit: async () => ({ recordVersion: 9 }) })
      target.setData({ remark: 'abcd' })
      const result = target.validate()
      expect(result.valid).toBe(false)
      expect(result.firstField).toBe('name')
      expect(target.canSubmit).toBe(false)

      const before = target.requestCount
      await expect(target.submit()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)
    })

    it('提交载荷：仅可见字段、只读字段保留、明细归一、编辑态带记录版本', async () => {
      const payloads: RenderContractPayload[] = []
      const target = loadedTarget({
        submit: async (input) => {
          payloads.push(input)
          return { recordVersion: 5 }
        },
      })
      target.setMeta({
        layout: RENDER_CONTRACT_LAYOUT,
        fields: RENDER_CONTRACT_FIELDS,
        permissions: { remark: { visible: false, editable: false } },
        readonly: false,
      })
      target.setData({ name: '甲', remark: 'abcd', amount: 12 })
      target.setDetails({ lines: [{ project_no: 'P1', junk: undefined }] })

      const result = await target.submit()
      expect(result).toEqual({ recordVersion: 5 })
      expect(target.phase).toBe('done')
      expect(payloads).toHaveLength(1)
      const payload = payloads[0]
      expect(payload?.formCode).toBe('leave')
      expect(payload?.mode).toBe('edit')
      // 不可见字段不入载荷；可见字段（含只读）保留。
      expect(payload?.data.remark).toBeUndefined()
      expect(payload?.data.name).toBe('甲')
      expect(payload?.data.amount).toBe(12)
      expect(payload?.details.lines).toHaveLength(1)
      expect(payload?.recordVersion).toBeUndefined()
    })

    it('提交成功清空错误并写回记录版本；失败保留本地数据', async () => {
      let fail = true
      const target = loadedTarget({
        submit: async () => {
          if (fail) {
            throw new Error('提交失败')
          }
          return { recordVersion: 7 }
        },
      })
      target.setData({ name: '甲', remark: 'abcd' })
      await expect(target.submit()).resolves.toBeUndefined()
      expect(target.phase).toBe('failed')
      expect(target.getFieldValue('name')).toBe('甲')

      fail = false
      await expect(target.retry()).resolves.toEqual({ recordVersion: 7 })
      expect(target.phase).toBe('done')
      expect(target.validation().valid).toBe(true)
    })

    it('进行中重复提交不动作', async () => {
      let release: () => void = () => undefined
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const target = loadedTarget({
        submit: async () => {
          await gate
          return { recordVersion: 1 }
        },
      })
      target.setData({ name: '甲', remark: 'abcd' })
      const pending = target.submit()
      expect(target.busy).toBe(true)
      await expect(target.submit()).resolves.toBeUndefined()
      release()
      await expect(pending).resolves.toEqual({ recordVersion: 1 })
      expect(target.requestCount).toBe(1)
    })

    it('明细区：列可编辑、行增删与单元格写入', async () => {
      const target = loadedTarget()
      expect(target.addDetailRow('lines', { project_no: 'P1' })).toBe(true)
      expect(target.detailRows('lines')).toHaveLength(1)

      expect(target.setDetailCell('lines', 0, 'project_no', 'P2')).toBe(true)
      expect(target.detailRows('lines')[0]?.project_no).toBe('P2')
      expect(target.setDetailCell('lines', 0, 'absent', 'x')).toBe(false)
      expect(target.setDetailCell('lines', 9, 'project_no', 'P3')).toBe(false)

      expect(target.addDetailRow('lines')).toBe(true)
      expect(target.detailRows('lines')).toHaveLength(2)
      expect(target.removeDetailRow('lines', 0)).toBe(true)
      expect(target.detailRows('lines')).toHaveLength(1)
      expect(target.removeDetailRow('lines', 9)).toBe(false)
    })

    it('只读态写入与明细操作均不动作', async () => {
      const target = loadedTarget()
      target.setOperators({ codes: [] })
      expect(target.setFieldValue('name', '乙')).toBe(false)
      expect(target.addDetailRow('lines')).toBe(false)
      expect(target.setDetailRows('lines', [])).toBe(false)
    })

    it('切换三态不改数据', async () => {
      const target = loadedTarget()
      target.setData({ name: '甲', remark: 'abcd' })
      expect(target.setMode('view')).toBe(true)
      expect(target.getFieldValue('name')).toBe('甲')
      expect(target.setMode('view')).toBe(false)
      expect(target.setMode('create')).toBe(true)
      expect(target.getFieldValue('name')).toBe('甲')
    })
  })
}
