// kiwi_id: 2527
/** 查询区派生领域纯函数用例（10_02）：顺序 / 跳过规则 / 控件映射 / 选项映射 / 缺省项。 */

import { describe, expect, it } from 'vitest'

import { FORM_QUERY_TYPES, formQueryFields } from '../src/domain/form-query'

describe('formQueryFields', () => {
  it('未配置查询区返回空清单', () => {
    expect(formQueryFields({})).toEqual([])
    expect(formQueryFields({ layout: { main: { sections: [] } } })).toEqual([])
  })

  it('顺序取布局查询字段而非字段 sort', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['status', 'name'] } },
      fields: [
        { key: 'name', label: '姓名', type: 'text' },
        { key: 'status', label: '状态', type: 'switch' },
      ],
    })
    expect(result.map((item) => item.key)).toEqual(['status', 'name'])
    expect(result.every((item) => item.query === true)).toBe(true)
  })

  it('失效引用与重复引用按归一结果跳过 / 去重', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['ghost', 'name', 'name', ''] } },
      fields: [{ key: 'name', label: '姓名', type: 'text' }],
    })
    expect(result.map((item) => item.key)).toEqual(['name'])
  })

  it('停用 / 待建列 / 建列失败与显式不可拖入的字段跳过', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['a', 'b', 'c', 'd'] } },
      fields: [
        { key: 'a', label: '停用', type: 'text', status: 'disabled' },
        { key: 'b', label: '待建列', type: 'text', status: 'pending' },
        { key: 'c', label: '失败', type: 'text', status: 'failed' },
        { key: 'd', label: '不可拖入', type: 'text', status: 'active', disabled: true },
      ],
    })
    expect(result).toEqual([])
  })

  it('类型不在白名单的字段跳过', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['file', 'dict', 'rich', 'text'] } },
      fields: [
        { key: 'file', label: '附件', type: 'file' },
        { key: 'dict', label: '字典', type: 'dict' },
        { key: 'rich', label: '富文本', type: 'richtext' },
        { key: 'text', label: '文本', type: 'text' },
      ],
    })
    expect(result.map((item) => item.key)).toEqual(['text'])
    expect(FORM_QUERY_TYPES).toContain('text')
  })

  it('控件映射：长文本落文本域、其余同名', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['longtext', 'number', 'datetime', 'switch'] } },
      fields: [
        { key: 'longtext', label: '备注', type: 'longtext' },
        { key: 'number', label: '金额', type: 'number' },
        { key: 'datetime', label: '日期', type: 'datetime' },
        { key: 'switch', label: '启用', type: 'switch' },
      ],
    })
    expect(result.map((item) => item.type)).toEqual(['textarea', 'number', 'datetime', 'switch'])
  })

  it('枚举字段的候选项取选项集快照，快照缺失即空选项', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['level', 'unset'] } },
      fields: [
        { key: 'level', label: '等级', type: 'option', optionSetKey: 'bms.demo.level' },
        { key: 'unset', label: '未注册', type: 'option_multi', optionSetKey: 'bms.demo.missing' },
      ],
      optionSets: [
        {
          optionSetKey: 'bms.demo.level',
          items: [
            { value: 'a', label: '甲' },
            { value: 'b', label: '乙' },
          ],
        },
      ],
    })
    expect(result[0]?.options).toEqual([
      { label: '甲', value: 'a' },
      { label: '乙', value: 'b' },
    ])
    expect(result[1]?.options).toEqual([])
  })

  it('枚举字段未带选项集标识时候选项为空', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['level'] } },
      fields: [{ key: 'level', label: '等级', type: 'option' }],
    })
    expect(result[0]?.options).toEqual([])
  })

  it('提示文案与默认值随字段属性下发', () => {
    const result = formQueryFields({
      layout: { query: { fields: ['name'] } },
      fields: [{ key: 'name', label: '姓名', type: 'text', placeholder: '请输入', defaultValue: '张三' }],
    })
    expect(result[0]).toMatchObject({ placeholder: '请输入', defaultValue: '张三' })
  })
})
