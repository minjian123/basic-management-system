// kiwi_id: 772
// 领域纯函数用例：渲染分发 / 三态与权限叠加 / 渲染计划 / 规则与校验 / 明细 / 载荷。
import { describe, expect, it } from 'vitest'

import {
  DEFAULT_DETAIL_COLUMNS,
  EMPTY_TEXT,
  FIELD_WIDGETS,
  FIELD_WIDGET_MAP,
  MASK_TEXT,
  buildFieldPlan,
  buildRenderPlan,
  buildSubmitPayload,
  compileFieldRules,
  countPlanFields,
  displayFieldText,
  fallbackDetailColumns,
  isKnownFieldType,
  isSectionColumnsValid,
  isSubmitAllowed,
  maskFieldText,
  mkFieldRules,
  normalizeDetailRows,
  normalizeDetailSet,
  normalizeField,
  normalizeFieldOverrides,
  normalizeRenderMetadata,
  normalizeRenderMode,
  resolveBaselineEditable,
  resolveFieldRenderState,
  resolveFieldWidget,
  sectionSpan,
  validateDetailRows,
  validateDetails,
  validateFieldValue,
  validateFormData,
  visibleFields,
} from '../src'
import type { FormField, FormLayout, LayoutEffective } from '../src'

/** 字段清单。 */
const fields: FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active', required: true },
  { key: 'remark', label: '备注', type: 'longtext', group: 'platform', status: 'active' },
  { key: 'amount', label: '金额', type: 'amount', group: 'platform', status: 'active' },
  {
    key: 'level',
    label: '等级',
    type: 'select',
    group: 'platform',
    status: 'active',
    options: [{ value: 'a', label: '甲' }],
  },
  { key: 'broken', label: '失效', type: 'text', group: 'tenant', status: 'failed' },
]

/** 基础布局（含分组与明细列）。 */
const layout: FormLayout = {
  main: {
    labelPosition: 'top',
    sections: [
      {
        key: 's1',
        title: '基本信息',
        columns: 2,
        fields: [{ key: 'name' }, { key: 'remark', colSpan: true }, { key: 'absent' }],
      },
      {
        key: 's2',
        title: '扩展',
        columns: 3,
        fields: [{ key: 'amount' }],
        groups: [{ key: 'g1', title: '分组', fields: [{ key: 'level' }] }],
      },
    ],
  },
  detail: { columns: [{ key: 'name', width: 200 }] },
}

/** 生效布局工厂。 */
function effectiveOf(input: Partial<LayoutEffective> = {}): LayoutEffective {
  return {
    layout,
    fields,
    level: 'tenant',
    source: 'tenant',
    readonly: false,
    fallback: false,
    ...input,
  }
}

describe('字段类型 → 控件语义键', () => {
  it('内建映射覆盖基础控件类与字段类', () => {
    expect(resolveFieldWidget('text')).toBe('text')
    expect(resolveFieldWidget('longtext')).toBe('textarea')
    expect(resolveFieldWidget('amount')).toBe('number')
    expect(resolveFieldWidget('percent')).toBe('number')
    expect(resolveFieldWidget('date')).toBe('datetime')
    expect(resolveFieldWidget('multi_select')).toBe('multi-select')
    expect(resolveFieldWidget('switch')).toBe('switch')
    expect(resolveFieldWidget('richtext')).toBe('richtext')
    expect(resolveFieldWidget('dept')).toBe('org-select')
    expect(resolveFieldWidget('tree')).toBe('tree-select')
    expect(resolveFieldWidget('user')).toBe('org-select')
    expect(resolveFieldWidget('post')).toBe('org-select')
    expect(resolveFieldWidget('org')).toBe('org-select')
    expect(resolveFieldWidget('transfer')).toBe('transfer')
    expect(resolveFieldWidget('cascader')).toBe('cascader')
    expect(resolveFieldWidget('tags')).toBe('tags')
    expect(resolveFieldWidget('captcha')).toBe('captcha')
    expect(resolveFieldWidget('dict')).toBe('dict-select')
    expect(resolveFieldWidget('dict_multi')).toBe('dict-multi')
    expect(resolveFieldWidget('file')).toBe('file-upload')
    expect(resolveFieldWidget('image')).toBe('image-upload')
  })

  it('上传引用属性透传（upload*）', () => {
    const field = normalizeField({
      key: 'attachment',
      type: 'file',
      uploadAccept: '.pdf,.png',
      uploadMaxSize: 2 * 1024 * 1024,
      uploadLimit: 3,
      uploadMultiple: true,
    })
    expect(field.uploadAccept).toBe('.pdf,.png')
    expect(field.uploadMaxSize).toBe(2 * 1024 * 1024)
    expect(field.uploadLimit).toBe(3)
    expect(field.uploadMultiple).toBe(true)
    const image = normalizeField({ key: 'avatar', type: 'image', uploadMultiple: false })
    expect(image.uploadMultiple).toBe(false)
  })

  it('字典引用属性透传（dictType）', () => {
    const field = normalizeField({ key: 'status', type: 'select', dictType: 'user_status' })
    expect(field.dictType).toBe('user_status')
    const multi = normalizeField({ key: 'tags', type: 'dict_multi', dictType: 'biz_type' })
    expect(multi.dictType).toBe('biz_type')
  })

  it('验证码属性透传（captchaKind / captchaScene，非法剔除）', () => {
    const field = normalizeField({ key: 'code', type: 'captcha', captchaKind: 'sms', captchaScene: 'bind' })
    expect(field.captchaKind).toBe('sms')
    expect(field.captchaScene).toBe('bind')
    const fallback = normalizeField({
      key: 'code2',
      type: 'captcha',
      captchaKind: 'unknown' as never,
      captchaScene: 'bogus' as never,
    })
    expect(fallback.captchaKind).toBeUndefined()
    expect(fallback.captchaScene).toBeUndefined()
  })

  it('表外类型回退纯文本且判为未知', () => {
    expect(resolveFieldWidget('wild_type')).toBe('plain')
    expect(isKnownFieldType('wild_type')).toBe(false)
    expect(isKnownFieldType('text')).toBe(true)
    expect(FIELD_WIDGETS).toContain('plain')
    expect(Object.keys(FIELD_WIDGET_MAP).length).toBeGreaterThan(20)
  })
})

describe('装载归一', () => {
  it('元数据缺省项补确定值并归一权限标记', () => {
    const meta = normalizeRenderMetadata({
      layout: { main: { sections: [{ fields: ['name'] }] } },
      fields: [{ key: 'name' }, { label: '无名' }],
      permissions: { name: { visible: false } },
    })
    expect(meta.level).toBe('tenant')
    expect(meta.source).toBe('empty')
    expect(meta.readonly).toBe(false)
    expect(meta.fields[0]?.type).toBe('text')
    expect(meta.fields[0]?.group).toBe('platform')
    expect(meta.fields[1]?.key).toBe('section-2')
    expect(meta.permissions).toEqual({ name: { visible: false } })

    const empty = normalizeRenderMetadata(undefined)
    expect(empty.fallback).toBe(true)
    expect(empty.readonly).toBe(true)
    expect(empty.fields).toEqual([])
  })

  it('字段归一剔非法状态并补缺省属性', () => {
    const field = normalizeField({ key: 'k', status: 'bogus', group: 'other', rules: [{ kind: 'bogus' }] as never }, 0)
    expect(field.status).toBeUndefined()
    expect(field.group).toBe('platform')
    expect(field.rules).toBeUndefined()
    expect(field.type).toBe('text')
  })

  it('覆盖归一与三态归一', () => {
    expect(normalizeFieldOverrides(undefined)).toEqual({})
    expect(normalizeFieldOverrides({ a: { required: true } })).toEqual({ a: { required: true } })
    expect(normalizeRenderMode('view')).toBe('view')
    expect(normalizeRenderMode('bogus')).toBe('create')
  })
})

describe('三态与权限叠加', () => {
  it('三态基线：查看态只读、强制只读覆盖三态', () => {
    expect(resolveBaselineEditable('create')).toBe(true)
    expect(resolveBaselineEditable('edit')).toBe(true)
    expect(resolveBaselineEditable('view')).toBe(false)
    expect(resolveBaselineEditable('edit', true)).toBe(false)
  })

  it('权限为终态且双向：可放宽查看态、可收紧编辑态', () => {
    const field = fields[0] as FormField
    const widened = resolveFieldRenderState({ field, mode: 'view', permission: { editable: true } })
    expect(widened.editable).toBe(true)
    expect(widened.displayOnly).toBe(true)

    const narrowed = resolveFieldRenderState({
      field,
      mode: 'edit',
      permission: { editable: false, required: true, mask: true },
    })
    expect(narrowed.editable).toBe(false)
    expect(narrowed.disabled).toBe(true)
    expect(narrowed.required).toBe(true)
    expect(narrowed.masked).toBe(true)

    const hidden = resolveFieldRenderState({ field, mode: 'edit', permission: { visible: false } })
    expect(hidden.visible).toBe(false)

    const shown = resolveFieldRenderState({
      field: { ...field, hidden: true },
      mode: 'edit',
      permission: { visible: true },
    })
    expect(shown.visible).toBe(true)
  })

  it('字段属性只读 / 隐藏在不注入权限时生效', () => {
    const readonlyField: FormField = { key: 'x', label: 'X', type: 'text', group: 'platform', readonly: true }
    const state = resolveFieldRenderState({ field: readonlyField, mode: 'edit' })
    expect(state.editable).toBe(false)
    expect(state.visible).toBe(true)
  })
})

describe('渲染计划', () => {
  it('分区 / 跨列 / 分组迁移 / 失效跳过 / 停用保留', () => {
    const plan = buildRenderPlan(effectiveOf())
    expect(plan.sections).toHaveLength(2)
    expect(plan.sections[0]?.columns).toBe(2)
    expect(plan.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
    expect(plan.sections[0]?.fields[1]?.colSpan).toBe(true)
    expect(plan.sections[1]?.groups).toHaveLength(1)
    expect(plan.sections[1]?.groups[0]?.fields.map((field) => field.key)).toEqual(['level'])
    expect(plan.sections[1]?.fields.map((field) => field.key)).toEqual(['amount', 'level'])
    expect(plan.unknownFields).toEqual(['absent'])
    expect(plan.disabledFields).toEqual([])
    expect(countPlanFields(plan)).toBe(4)
  })

  it('不可见字段保留在计划并记入 hiddenFields', () => {
    const plan = buildRenderPlan(effectiveOf(), { permissions: { remark: { visible: false } } })
    expect(plan.hiddenFields).toEqual(['remark'])
    expect(plan.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
    expect(visibleFields(plan).map((field) => field.key)).toEqual(['name', 'amount', 'level'])
  })

  it('停用字段只读保留并记入 disabledFields', () => {
    const plan = buildRenderPlan({
      ...effectiveOf(),
      layout: {
        main: { labelPosition: 'top', sections: [{ key: 's1', title: '', columns: 1, fields: [{ key: 'broken' }] }] },
      },
    })
    expect(plan.disabledFields).toEqual(['broken'])
    expect(plan.sections[0]?.fields[0]?.key).toBe('broken')
  })

  it('明细列按布局下发；未配置时回退默认列', () => {
    const configured = buildRenderPlan(effectiveOf())
    expect(configured.detailColumns.map((column) => column.key)).toEqual(['name'])
    expect(configured.detailColumns[0]?.title).toBe('姓名')
    expect(configured.detailFallback).toBe(false)

    const fallback = buildRenderPlan({
      ...effectiveOf(),
      layout: {
        main: {
          labelPosition: 'top',
          sections: [{ key: 'd', title: '', columns: 3, fields: [{ key: 'name' }, { key: 'remark' }] }],
        },
      },
    })
    expect(fallback.detailFallback).toBe(true)
    expect(fallback.detailColumns.map((column) => column.key)).toEqual(['name', 'remark'])
  })

  it('明细列回退上限与只读态', () => {
    const many = Array.from({ length: 10 }, (_, index) => ({ key: `f${index}` }))
    const planFields = many.map((item) =>
      buildFieldPlan({ field: { key: item.key, label: item.key, type: 'text', group: 'platform' }, mode: 'edit' }),
    )
    const columns = fallbackDetailColumns([
      { key: 's1', title: '', columns: 3, groups: [], fields: planFields, ungroupedFields: planFields },
    ])
    expect(columns).toHaveLength(DEFAULT_DETAIL_COLUMNS)

    const readonlyPlan = buildRenderPlan(effectiveOf({ readonly: true }))
    expect(readonlyPlan.readonly).toBe(true)
    expect(readonlyPlan.detailColumns[0]?.editable).toBe(false)
  })

  it('空布局回退标记透出', () => {
    const plan = buildRenderPlan(
      effectiveOf({ layout: { main: { labelPosition: 'top', sections: [] } }, fallback: true }),
    )
    expect(plan.fallback).toBe(true)
    expect(plan.sections).toEqual([])
  })
})

describe('规则与校验', () => {
  it('必填规则仅在可见可编辑时产出，显式规则照搬', () => {
    const field = fields[0] as FormField
    expect(mkFieldRules(field).map((rule) => rule.kind)).toEqual(['required'])
    expect(
      mkFieldRules(field, {
        state: { visible: true, editable: false, disabled: true, required: true, masked: false, displayOnly: false },
      }),
    ).toEqual([])

    const withRules: FormField = { ...field, rules: [{ kind: 'length', min: 2, max: 4 }] }
    expect(mkFieldRules(withRules).map((rule) => rule.kind)).toEqual(['required', 'length'])
  })

  it('规则编译复用既有校验器（必填 / 长度 / 范围 / 正则）', () => {
    const validators = compileFieldRules([
      { kind: 'required' },
      { kind: 'length', min: 2, max: 4, message: '长度错' },
      { kind: 'range', min: 1, max: 10, message: '范围错' },
      { kind: 'pattern', pattern: '^a', message: '格式错' },
      { kind: 'options' },
    ])
    expect(validators).toHaveLength(4)
    expect(validators[0]?.(undefined)).toBe('必填')
    expect(validators[1]?.('x')).toBe('长度错')
    expect(validators[2]?.(99)).toBe('范围错')
    expect(validators[3]?.('b')).toBe('格式错')

    // 非法正则不产出校验器（不抛错）。
    expect(compileFieldRules([{ kind: 'pattern' }])).toHaveLength(0)
  })

  it('单字段校验：只读或不可见跳过、必填 / 长度 / 选项集命中', () => {
    const required: FormField = { key: 'name', label: '姓名', type: 'text', group: 'platform', required: true }
    expect(validateFieldValue(required, '', { mode: 'edit' })).toBe('必填')
    expect(validateFieldValue(required, 'ok', { mode: 'edit' })).toBeUndefined()
    expect(validateFieldValue(required, '', { mode: 'view' })).toBeUndefined()
    expect(validateFieldValue(required, '', { mode: 'edit', permission: { editable: false } })).toBeUndefined()

    const withOptions: FormField = {
      key: 'level',
      label: '等级',
      type: 'select',
      group: 'platform',
      options: [{ value: 'a', label: '甲' }],
    }
    expect(validateFieldValue(withOptions, 'b', { mode: 'edit' })).toBe('选项不在可选范围内')
    expect(validateFieldValue(withOptions, 'a', { mode: 'edit' })).toBeUndefined()
    expect(validateFieldValue(withOptions, ['a'], { mode: 'edit' })).toBeUndefined()
  })

  it('全量校验定位首个错误字段并汇总文案', () => {
    const plan = buildRenderPlan(effectiveOf())
    const result = validateFormData(plan, {})
    expect(result.valid).toBe(false)
    expect(result.firstField).toBe('name')
    expect(result.message).toContain('name')

    const ok = validateFormData(plan, { name: '甲' })
    expect(ok.valid).toBe(true)
    expect(ok.firstField).toBeUndefined()
    expect(ok.message).toBe('')
  })

  it('明细行级校验定位 `页签 → 行 → 列`', () => {
    const plan = buildRenderPlan({
      ...effectiveOf(),
      layout: {
        main: { labelPosition: 'top', sections: [{ key: 's', title: '', columns: 2, fields: [{ key: 'name' }] }] },
        detail: { columns: [{ key: 'name' }, { key: 'remark' }] },
      },
    })
    const result = validateDetailRows(plan.detailColumns, [{ name: 'P1' }, { name: '' }], 'lines')
    expect(result.valid).toBe(false)
    expect(result.errors[0]?.detailKey).toBe('lines')
    expect(result.errors[0]?.index).toBe(1)
    expect(result.errors[0]?.field).toBe('name')

    const all = validateDetails(plan, { lines: [{ name: '' }] })
    expect(all.valid).toBe(false)
    expect(validateDetails(plan, { lines: [{ name: 'P1' }] }).valid).toBe(true)
  })
})

describe('展示与明细归一', () => {
  it('脱敏与空值展示', () => {
    expect(maskFieldText('明文')).toBe(MASK_TEXT)
    expect(maskFieldText('')).toBe(EMPTY_TEXT)
    expect(maskFieldText(null)).toBe(EMPTY_TEXT)
    expect(displayFieldText(['a', 'b'])).toBe('a、b')
    expect(displayFieldText(0)).toBe('0')
    expect(displayFieldText(undefined)).toBe(EMPTY_TEXT)
  })

  it('明细行归一剔除非对象行并补缺省页签', () => {
    expect(normalizeDetailRows([{ a: 1 }, null, 'x', [1], undefined])).toEqual([{ a: 1 }])
    expect(normalizeDetailSet({ lines: [{ a: 1 }] }, ['lines', 'extra'])).toEqual({ lines: [{ a: 1 }], extra: [] })
    expect(normalizeDetailSet(undefined)).toEqual({})
  })
})

describe('提交载荷与许可', () => {
  it('只含可见字段、保留只读字段与默认值、明细归一', () => {
    const plan = buildRenderPlan(effectiveOf(), { permissions: { remark: { visible: false } } })
    const payload = buildSubmitPayload({
      formCode: 'leave',
      mode: 'edit',
      recordId: 9,
      recordVersion: 3,
      plan,
      data: { name: '甲', remark: '隐藏', extra: 1 },
      details: { lines: [{ name: 'P1' } as Record<string, unknown>, null as never] },
    })
    expect(payload.formCode).toBe('leave')
    expect(payload.mode).toBe('edit')
    expect(payload.recordId).toBe(9)
    expect(payload.recordVersion).toBe(3)
    expect(payload.data.remark).toBeUndefined()
    expect(payload.data.extra).toBeUndefined()
    expect(payload.data.name).toBe('甲')
    expect(payload.details.lines).toEqual([{ name: 'P1' }])
  })

  it('新增态不带记录版本', () => {
    const plan = buildRenderPlan(effectiveOf())
    const payload = buildSubmitPayload({ formCode: 'leave', mode: 'create', recordVersion: 3, plan })
    expect(payload.recordVersion).toBeUndefined()
    expect(payload.recordId).toBeUndefined()
  })

  it('提交许可：只读 / 进行中 / 校验未过均不允许', () => {
    const valid = { valid: true, errors: [], firstField: undefined, message: '' }
    const invalid = { valid: false, errors: [{ field: 'a', message: '必填' }], firstField: 'a', message: '必填' }
    expect(isSubmitAllowed({ readonly: false, busy: false, validation: valid })).toBe(true)
    expect(isSubmitAllowed({ readonly: true, busy: false, validation: valid })).toBe(false)
    expect(isSubmitAllowed({ readonly: false, busy: true, validation: valid })).toBe(false)
    expect(isSubmitAllowed({ readonly: false, busy: false, validation: invalid })).toBe(false)
    expect(
      isSubmitAllowed({
        readonly: false,
        busy: false,
        validation: valid,
        detailValidation: { valid: false, errors: [], message: '' },
      }),
    ).toBe(false)
  })

  it('栅格工具：列数合法性与跨度换算', () => {
    expect(isSectionColumnsValid(2)).toBe(true)
    expect(isSectionColumnsValid(9)).toBe(false)
    expect(sectionSpan(2)).toBe(12)
    expect(sectionSpan(9)).toBe(8)
  })
})
