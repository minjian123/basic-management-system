// kiwi_id: 2293
/**
 * 契约用例：字典判定（08_01）——`isDictKind` 唯一判定、清单归一 `isDict`（派生字段 + 缺省回落）、
 * 能力层消费位 `BasePageRoute.isDictPage` / `isDictDataSource`。
 */

import { describe, expect, it } from 'vitest'

import { BasePageRoute, DICT_KIND, isDictKind, normalizeDataSourceRecord, normalizeFormKeyRecord } from '../src/index'

/** 具体页面路由（可实例化）。 */
class PageRoute extends BasePageRoute {}

describe('domain/page-route 字典判定', () => {
  it('isDictKind：字典为真，其余（表单 / 空 / 未知 / 缺省）为假', () => {
    expect(DICT_KIND).toBe('dict')
    expect(isDictKind('dict')).toBe(true)
    expect(isDictKind('form')).toBe(false)
    expect(isDictKind('')).toBe(false)
    expect(isDictKind('other')).toBe(false)
    expect(isDictKind(undefined)).toBe(false)
  })

  it('数据源归一：显式 is_dict 直取；缺省回落 kind 判定；兼容 camelCase', () => {
    const explicit = normalizeDataSourceRecord({ data_source_key: 'role', kind: 'form', is_dict: true })
    expect(explicit?.isDict).toBe(true)
    const camel = normalizeDataSourceRecord({ dataSourceKey: 'role', kind: 'dict', isDict: false })
    expect(camel?.isDict).toBe(false)
    const fallbackDict = normalizeDataSourceRecord({ data_source_key: 'role', kind: 'dict' })
    expect(fallbackDict?.isDict).toBe(true)
    const fallbackForm = normalizeDataSourceRecord({ data_source_key: 'order', kind: 'form' })
    expect(fallbackForm?.isDict).toBe(false)
    // 非布尔值（字符串 / 数字）不当作显式声明，继续回落 kind
    const nonBoolean = normalizeDataSourceRecord({ data_source_key: 'role', is_dict: 'yes', kind: 'dict' })
    expect(nonBoolean?.isDict).toBe(true)
  })

  it('表单标识归一：显式 is_dict 直取；缺省回落 kind 判定；未知 kind 视为非字典', () => {
    const explicit = normalizeFormKeyRecord({ form_key: 'role', kind: 'dict', is_dict: false })
    expect(explicit?.isDict).toBe(false)
    const fallbackDict = normalizeFormKeyRecord({ form_key: 'role' })
    expect(fallbackDict?.isDict).toBe(true)
    const unknown = normalizeFormKeyRecord({ form_key: 'role', kind: 'other' })
    expect(unknown?.isDict).toBe(false)
    expect(normalizeFormKeyRecord(null)).toBeUndefined()
  })
})

describe('BasePageRoute 字典消费位', () => {
  it('清单未装载即非字典（占位零请求语义不变）', () => {
    const route = new PageRoute()
    expect(route.isDictPage('role')).toBe(false)
    expect(route.isDictDataSource('role')).toBe(false)
  })

  it('装载后：字典项为真、非字典项与未命中为假', async () => {
    const route = new PageRoute()
    route.adapter = {
      loadDataSources: async () => ({
        items: [
          { data_source_key: 'role', kind: 'dict', origin: 'platform', data_source: 'platform', is_dict: true },
          { data_source_key: 'order', kind: 'form', origin: 'product', data_source: 'biz.order', is_dict: false },
        ],
      }),
      loadFormKeys: async () => ({
        items: [
          { form_key: 'role', kind: 'dict', table: 'sys_role', data_source_key: 'role', is_dict: true },
          { form_key: 'order', kind: 'form', table: 'biz_order', data_source_key: 'order', is_dict: false },
        ],
      }),
    }
    await route.load()
    expect(route.isDictPage('role')).toBe(true)
    expect(route.isDictPage('order')).toBe(false)
    expect(route.isDictPage('ghost')).toBe(false)
    expect(route.isDictDataSource('role')).toBe(true)
    expect(route.isDictDataSource('order')).toBe(false)
    expect(route.isDictDataSource('ghost')).toBe(false)
  })
})
