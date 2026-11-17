// kiwi_id: 2524
/** 审计 HTTP 适配器与差异组合式（09_01）：列表参数 / 详情 / 链校验 / 分组映射。 */

import { effectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createHttpAuditQuery, useAuditDiff } from '../src'

/** 统一响应包装。 */
function wrap(data: unknown): unknown {
  return { code: 0, message: '', data }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createHttpAuditQuery（09_01）', () => {
  it('列表参数转 snake_case；详情与链校验路径正确', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void url
      void init
      return { ok: true, json: async () => wrap({ list: [], total: 0 }) }
    })
    vi.stubGlobal('fetch', fetchMock)
    const query = createHttpAuditQuery({ endpoint: '/api/v1', headers: { Authorization: 'Bearer t' } })

    await query.page({
      tableName: 'sys_user',
      recordId: '9',
      operatorId: '7',
      occurredFrom: '2026-01-01T00:00:00Z',
      occurredTo: '2026-02-01T00:00:00Z',
      page: 2,
      size: 50,
    })
    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/api/v1/audit/data-changes?')
    expect(url).toContain('table_name=sys_user')
    expect(url).toContain('record_id=9')
    expect(url).toContain('operator_id=7')
    expect(url).toContain('occurred_from=2026-01-01T00%3A00%3A00Z')
    expect(url).toContain('page=2')
    expect(url).toContain('size=50')

    await query.detail('123')
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe('/api/v1/audit/data-changes/123')

    await query.verify('202601,202602')
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('/audit/chain/verify?months=202601%2C202602')
  })
})

describe('useAuditDiff（09_01）', () => {
  it('按 event_id 分组为记录；选中映射字段差异并解析 JSON 值', async () => {
    const rows = [
      {
        id: '11',
        event_id: 'evt-1',
        table_name: 'sys_user',
        record_id: '9',
        field: 'name',
        old_value: '"旧名"',
        new_value: '"新名"',
        operator_id: '7',
        occurred_at: '2026-01-02T03:04:05Z',
        prev_hash: 'p1',
        record_hash: 'r1',
      },
      {
        id: '12',
        event_id: 'evt-1',
        table_name: 'sys_user',
        record_id: '9',
        field: 'status',
        old_value: '"enabled"',
        new_value: '"disabled"',
        occurred_at: '2026-01-02T03:04:05Z',
        prev_hash: 'p1',
        record_hash: 'r2',
      },
    ]
    const scope = effectScope(true)
    const api = scope.run(() =>
      useAuditDiff({
        ready: true,
        query: {
          page: async () => ({ list: rows, total: 2, page: 1, size: 20 }),
          detail: async () => rows[0],
          verify: async () => ({ valid: true }),
        },
      }),
    )
    expect(api).toBeDefined()
    await api!.load({ page: 1 })
    expect(api!.records.value).toHaveLength(1)
    expect(api!.records.value[0]).toMatchObject({ id: 'evt-1', tableName: 'sys_user', fields: 2, operator: '7' })

    api!.select('evt-1')
    expect(api!.diff.value).toHaveLength(2)
    expect(api!.diff.value[0]).toMatchObject({ field: 'name', oldValue: '旧名', newValue: '新名' })
    expect(api!.prevHash.value).toBe('p1')
    expect(api!.recordHash.value).toBe('r2')

    await api!.verify()
    expect(api!.chainVerified.value).toBe(true)
    scope.stop()
  })

  it('未就绪零请求；链校验失败给断裂月份文案', async () => {
    const page = vi.fn()
    const scope = effectScope(true)
    const idle = scope.run(() => useAuditDiff({ ready: false, query: { page, detail: vi.fn(), verify: vi.fn() } }))
    await idle!.load({})
    expect(page).not.toHaveBeenCalled()

    const failing = scope.run(() =>
      useAuditDiff({
        ready: true,
        query: {
          page: async () => ({ list: [], total: 0 }),
          detail: async () => undefined,
          verify: async () => ({ valid: false, broken_month: '202601' }),
        },
      }),
    )
    await failing!.verify()
    expect(failing!.chainVerified.value).toBe(false)
    expect(failing!.chainMessage.value).toContain('202601')
    scope.stop()
  })
})

