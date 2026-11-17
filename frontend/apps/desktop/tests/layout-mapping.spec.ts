// kiwi_id: 2527
/** 设计器页模型归并用例（10_02）：字段键派生 / 字段合并与排序 / 属性草稿与清洗 / 行主键定位。 */

import { describe, expect, it } from 'vitest'

import type { ExtFieldItem, LayoutEffectiveResponse } from '@/api/formDesign'
import {
  attrsPayload,
  cleanAttrs,
  designerFields,
  extFieldKey,
  pickRowId,
  toAttrDraft,
  toTenantField,
} from '@/views/system/formdesign/layoutMapping'

/** 自建字段行桩。 */
function extItem(overrides: Partial<ExtFieldItem> = {}): ExtFieldItem {
  return {
    id: '1',
    form_code: 'user',
    field_key: 'project_no',
    name: '项目编号',
    type: 'text',
    sort: 3,
    status: 'enabled',
    ddl_status: 'active',
    column_name: 'ext_project_no',
    table_name: 'sys_user',
    names: {},
    option_set_key: null,
    ...overrides,
  }
}

/** 生效布局响应桩。 */
const RESPONSE: LayoutEffectiveResponse = {
  layout: {},
  fields: [
    { key: 'status', label: '状态', type: 'switch', group: 'platform', sort: 2, status: 'active', disabled: false, attrs: {} },
    { key: 'name', label: '姓名', type: 'text', group: 'platform', sort: 2, status: 'active', disabled: true, attrs: { required: true } },
    { key: 'ignored', label: '自建', type: 'text', group: 'tenant', sort: 1, status: 'active', disabled: false, attrs: {} },
  ],
  level: 'role',
  source: 'tenant',
  readonly: true,
  fallback: false,
}

describe('extFieldKey', () => {
  it('驼峰 / 空格 / 点号转蛇形，非法字符剔除', () => {
    expect(extFieldKey('projectNo')).toBe('project_no')
    expect(extFieldKey('Project No.')).toBe('project_no')
    expect(extFieldKey('A_B')).toBe('a_b')
  })

  it('派生不出合法键时返回空串（首字符非字母 / 全中文 / 纯符号）', () => {
    expect(extFieldKey('')).toBe('')
    expect(extFieldKey('1abc')).toBe('')
    expect(extFieldKey('项目编号')).toBe('')
    expect(extFieldKey('---')).toBe('')
  })

  it('超长名称截断到 60 字符以内', () => {
    const key = extFieldKey('a'.repeat(80))
    expect(key).toHaveLength(60)
  })
})

describe('toTenantField', () => {
  it('已生效且启用可拖入；停用 / 建列失败不可拖入', () => {
    expect(toTenantField(extItem())).toMatchObject({ key: 'project_no', group: 'tenant', status: 'active' })
    expect(toTenantField(extItem()).disabled).toBeUndefined()

    const disabled = toTenantField(extItem({ status: 'disabled' }))
    expect(disabled).toMatchObject({ status: 'disabled', disabled: true })

    const failed = toTenantField(extItem({ ddl_status: 'failed' }))
    expect(failed).toMatchObject({ status: 'failed', disabled: true })
  })
})

describe('designerFields', () => {
  it('平台字段在前（同 sort 按键升序），自建字段在后；属性随字段展平', () => {
    const fields = designerFields(RESPONSE, [extItem({ sort: 1 }), extItem({ field_key: 'aaa', name: '前', sort: 0 })])
    expect(fields.map((field) => field.key)).toEqual(['name', 'status', 'aaa', 'project_no'])
    expect(fields[0]).toMatchObject({ key: 'name', required: true, disabled: true })
    expect(fields[1]).toMatchObject({ key: 'status' })
    expect(fields[1]?.required).toBeUndefined()
  })

  it('字段缺省 attrs 与空清单按空集处理', () => {
    const fields = designerFields({ ...RESPONSE, fields: undefined }, [])
    expect(fields).toEqual([])
  })

  it('字段缺省 attrs 不抛错；自建字段同 sort 按键升序', () => {
    const noAttrs = designerFields(
      {
        ...RESPONSE,
        fields: [{ key: 'name', label: '姓名', type: 'text', group: 'platform', sort: 1, status: 'active', disabled: false }],
      },
      [],
    )
    expect(noAttrs[0]?.required).toBeUndefined()

    const ties = designerFields({ ...RESPONSE, fields: [] }, [
      extItem({ field_key: 'zzz', sort: 1 }),
      extItem({ field_key: 'aaa', sort: 1 }),
    ])
    expect(ties.map((field) => field.key)).toEqual(['aaa', 'zzz'])
  })
})

describe('toAttrDraft', () => {
  it('未配置返回空补丁', () => {
    expect(toAttrDraft(undefined)).toEqual({})
    expect(toAttrDraft({})).toEqual({})
  })

  it('已配置项全部带出，空串与假值不带', () => {
    expect(
      toAttrDraft({
        required: true,
        placeholder: '请输入',
        defaultValue: 5,
        rules: [{ kind: 'length', max: 9 }],
        optionSetKey: 'bms.demo.level',
        widget: 'radio',
        readonly: true,
        hidden: true,
      }),
    ).toEqual({
      required: true,
      placeholder: '请输入',
      defaultValue: 5,
      rules: [{ kind: 'length', max: 9 }],
      optionSetKey: 'bms.demo.level',
      widget: 'radio',
      readonly: true,
      hidden: true,
    })
    expect(
      toAttrDraft({ placeholder: '', defaultValue: '', rules: [], optionSetKey: '', widget: '', required: false }),
    ).toEqual({})
  })
})

describe('cleanAttrs', () => {
  it('保留有效项，丢弃空串 / 假值 / 空规则', () => {
    expect(
      cleanAttrs({
        required: true,
        placeholder: '提示',
        defaultValue: 'x',
        rules: [{ kind: 'range', min: 1 }],
        optionSetKey: 'bms.demo.level',
        widget: 'tag',
        readonly: true,
        hidden: true,
      }),
    ).toEqual({
      required: true,
      placeholder: '提示',
      defaultValue: 'x',
      rules: [{ kind: 'range', min: 1 }],
      optionSetKey: 'bms.demo.level',
      widget: 'tag',
      readonly: true,
      hidden: true,
    })
    expect(cleanAttrs({ required: false, placeholder: '', rules: [] })).toEqual({})
  })
})

describe('attrsPayload', () => {
  it('只带有非空属性的字段，字段类型随行', () => {
    const fields = designerFields(RESPONSE, [extItem()])
    const items = attrsPayload(fields, {
      name: { required: true },
      status: { placeholder: '' },
      'aaa': {},
    })
    expect(items).toEqual([{ field_key: 'name', field_type: 'text', attrs: { required: true } }])
  })

  it('草稿缺项按空属性处理（不落行）', () => {
    const fields = designerFields(RESPONSE, [])
    expect(attrsPayload(fields, {})).toEqual([])
  })
})

describe('pickRowId', () => {
  it('按层级与角色取行主键，无行返回空串', () => {
    const rows = [
      { id: '1', scope: 'tenant', role_id: '0' },
      { id: '2', scope: 'role', role_id: '88' },
    ]
    expect(pickRowId(rows, 'tenant')).toBe('1')
    expect(pickRowId(rows, 'role', '88')).toBe('2')
    expect(pickRowId(rows, 'platform')).toBe('')
  })
})
