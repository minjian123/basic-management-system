// kiwi_id: 2524
/** 审计领域纯函数（09_01）：行归一 / 事件分组 / JSON 值解析。 */

import { describe, expect, it } from 'vitest'

import { groupAuditRows, normalizeAuditRow, normalizeAuditRows, parseAuditJson } from '@bms/core'

/** 后端字段行样本。 */
function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: '1',
    event_id: 'evt-1',
    table_name: 'sys_user',
    record_id: '9',
    field: 'name',
    old_value: '"a"',
    new_value: '"b"',
    operator_id: '7',
    occurred_at: '2026-01-01T00:00:00Z',
    prev_hash: 'p',
    record_hash: 'r',
    ...overrides,
  }
}

describe('审计领域纯函数（09_01）', () => {
  it('归一行（兼容 snake_case；缺主键 / 事件 / 表名 / 字段丢弃）', () => {
    const normalized = normalizeAuditRow(row())
    expect(normalized).toMatchObject({ id: '1', eventId: 'evt-1', tableName: 'sys_user', field: 'name' })
    expect(normalizeAuditRow(row({ id: undefined }))).toBeUndefined()
    expect(normalizeAuditRow(row({ event_id: '' }))).toBeUndefined()
    expect(normalizeAuditRow('bad')).toBeUndefined()
  })

  it('归一批量（支持 list / items / data 包装）', () => {
    expect(normalizeAuditRows([row(), row({ id: '2' })])).toHaveLength(2)
    expect(normalizeAuditRows({ list: [row()] })).toHaveLength(1)
    expect(normalizeAuditRows({ items: [row()] })).toHaveLength(1)
    expect(normalizeAuditRows({ data: [row()] })).toHaveLength(1)
    expect(normalizeAuditRows(null)).toHaveLength(0)
  })

  it('按 event_id 分组（哈希取首尾；不同事件各自成组）', () => {
    const rows = [
      normalizeAuditRow(row({ id: '1', record_hash: 'r1' })),
      normalizeAuditRow(row({ id: '2', field: 'status', record_hash: 'r2' })),
      normalizeAuditRow(row({ id: '3', event_id: 'evt-2' })),
    ].filter((entry) => entry !== undefined)
    const groups = groupAuditRows(rows)
    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({ eventId: 'evt-1', prevHash: 'p', recordHash: 'r2' })
    expect(groups[0]?.rows).toHaveLength(2)
    expect(groups[1]?.eventId).toBe('evt-2')
  })

  it('解析 JSON 值（失败保留原文；空值 undefined）', () => {
    expect(parseAuditJson('"x"')).toBe('x')
    expect(parseAuditJson('{"a":1}')).toEqual({ a: 1 })
    expect(parseAuditJson('***')).toBe('***')
    expect(parseAuditJson('')).toBeUndefined()
    expect(parseAuditJson(undefined)).toBeUndefined()
  })
})
