/** 契约基类用例（02-5）：稳定序列化 / 实体 / 分页查询 / 模块 API。 */

import { describe, expect, it } from 'vitest'

import { BaseApi, BaseDataObject, BaseEntity, BasePageQuery, stableStringify } from '../src'

class DemoData extends BaseDataObject {
  b = 1
  a = 2
}

class DemoEntity extends BaseEntity {
  readonly id = '1001'
  readonly deletedAt: string | null

  constructor(deletedAt: string | null = null) {
    super()
    this.deletedAt = deletedAt
  }
}

class DemoApi extends BaseApi {
  readonly pathPrefix = '/api/v1/users'

  resolve(sub: string): string {
    return this.path(sub)
  }
}

describe('stableStringify 稳定序列化', () => {
  it('对象键排序 / 数组 / 标量', () => {
    expect(stableStringify({ b: 1, a: 2 })).toBe('{"a":2,"b":1}')
    expect(stableStringify([2, 1])).toBe('[2,1]')
    expect(stableStringify('x')).toBe('"x"')
  })
})

describe('BaseDataObject / BaseEntity / BasePageQuery', () => {
  it('数据对象稳定序列化（键排序）', () => {
    const json = new DemoData().toStableJSON()
    expect(json.indexOf('"a":2')).toBeLessThan(json.indexOf('"b":1'))
  })

  it('实体：标识 / 版本 / 软删除回显', () => {
    const entity = new DemoEntity()
    expect(entity.id).toBe('1001')
    expect(entity.isDeleted).toBe(false)
    expect(new DemoEntity('2026-01-01T00:00:00Z').isDeleted).toBe(true)
  })

  it('分页查询：页码 / 页长 / 偏移', () => {
    const query = new BasePageQuery()
    expect([query.page, query.size, query.offset]).toEqual([1, 20, 0])
    query.page = 3
    expect(query.offset).toBe(40)
  })
})

describe('BaseApi 模块 API 基类', () => {
  it('路径前缀拼接与幂等键', () => {
    const api = new DemoApi()
    expect(api.resolve('/1')).toBe('/api/v1/users/1')
    expect(api.createIdempotencyKey()).toContain('/api/v1/users')
  })
})
