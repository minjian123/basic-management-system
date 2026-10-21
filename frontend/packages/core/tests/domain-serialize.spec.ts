// kiwi_id: 2334
// 领域纯函数用例：整数 id 序列化豁免（字典字段提交保精度）。
import { describe, expect, it } from 'vitest'

import { stableStringify, stringifyIntegerIds } from '../src'

/** 19 位雪花 id（超 JS 安全整数）。 */
const BIG_ID = '1790000000000000001'

describe('整数 id 序列化豁免', () => {
  it('字典字段 id 写成裸数字字面量（精度无损）', () => {
    const text = stringifyIntegerIds({ data: { region_id: BIG_ID, name: '甲' } }, ['data.region_id'])
    expect(text).toBe('{"data":{"region_id":1790000000000000001,"name":"甲"}}')
  })

  it('多值数组与明细通配路径逐项处理', () => {
    const text = stringifyIntegerIds(
      {
        data: { ids: [BIG_ID, '2'] },
        details: { lines: [{ item_id: '3' }], other: [{ item_id: BIG_ID }] },
      },
      ['data.ids', 'details.*.item_id'],
    )
    expect(text).toBe(
      '{"data":{"ids":[1790000000000000001,2]},"details":{"lines":[{"item_id":3}],"other":[{"item_id":1790000000000000001}]}}',
    )
  })

  it('空值与安全整数：空串转 null、安全整数原样、数组空项转 null', () => {
    expect(stringifyIntegerIds({ data: { a: '', b: null, c: 12 } }, ['data.a', 'data.b', 'data.c'])).toBe(
      '{"data":{"a":null,"b":null,"c":12}}',
    )
    expect(stringifyIntegerIds({ data: { ids: [undefined] } }, ['data.ids'])).toBe('{"data":{"ids":[null]}}')
    expect(stringifyIntegerIds({ data: {} }, ['data.a'])).toBe('{"data":{}}')
  })

  it('未命中路径按标准 JSON（含 undefined 省略与嵌套）', () => {
    expect(stringifyIntegerIds({ a: [1, '2', null], b: undefined, c: { d: true } }, ['x.y'])).toBe(
      '{"a":[1,"2",null],"c":{"d":true}}',
    )
  })

  it('非法 id 抛错（非数字串 / 非安全整数 / 非标量）', () => {
    expect(() => stringifyIntegerIds({ data: { id: 'abc' } }, ['data.id'])).toThrow(/字典字段 data\.id/)
    expect(() => stringifyIntegerIds({ data: { id: '1.5' } }, ['data.id'])).toThrow()
    expect(() => stringifyIntegerIds({ data: { id: 2 ** 60 } }, ['data.id'])).toThrow()
    expect(() => stringifyIntegerIds({ data: { id: {} } }, ['data.id'])).toThrow()
    expect(() => stringifyIntegerIds({ data: { id: [-1] } }, ['data.id'])).toThrow()
  })

  it('顶层标量与路径段数不一致回退标准序列化', () => {
    expect(stringifyIntegerIds('x', ['data.id'])).toBe('"x"')
    expect(stringifyIntegerIds({ data: { id: '1' } }, ['data.id.extra'])).toBe('{"data":{"id":"1"}}')
  })

  it('不可序列化值降级（稳定序列化 / 整数序列化顶层 undefined）', () => {
    expect(stableStringify(undefined)).toBe('undefined')
    expect(stableStringify(null)).toBe('null')
    expect(stableStringify({ b: 1, a: [2] })).toBe('{"a":[2],"b":1}')
    expect(stringifyIntegerIds(undefined, [])).toBe('null')
  })
})
