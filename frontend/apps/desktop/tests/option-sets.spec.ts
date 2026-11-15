// kiwi_id: 2504
/** 选项集快照映射用例（09-03-1）：契约 snake_case → 前端 camelCase，可选字段归一。 */

import { describe, expect, it, vi } from 'vitest'

import { fetchOptionSetIndex, toOptionSetSnapshot } from '@/api/optionSets'
import { get } from '@/api/request'

vi.mock('@/api/request', () => ({ get: vi.fn() }))

const mockedGet = vi.mocked(get)

describe('选项集快照映射（09-03-1）', () => {
  it('契约字段映射：option_set_key / label_key → camelCase；可选字段归一', () => {
    const snapshot = toOptionSetSnapshot({
      option_set_key: 'bms.tenant.status',
      name: '租户状态',
      namespace: 'bms',
      version: 1,
      items: [
        {
          value: 'active',
          label: '启用',
          label_key: 'bms.tenant.status.active',
          color: 'success',
          disabled: false,
          sort: 20,
        },
        {
          value: 'deleted',
          label: '已注销',
          label_key: null,
          color: null,
          disabled: true,
          sort: 40,
        },
      ],
    })

    expect(snapshot.optionSetKey).toBe('bms.tenant.status')
    expect(snapshot.items[0]).toEqual({
      value: 'active',
      label: '启用',
      labelKey: 'bms.tenant.status.active',
      color: 'success',
      sort: 20,
    })
    expect(snapshot.items[1]).toEqual({ value: 'deleted', label: '已注销', disabled: true, sort: 40 })
  })

  it('拉取并按 optionSetKey 建索引', async () => {
    mockedGet.mockResolvedValue({
      items: [
        {
          option_set_key: 'bms.datasource.kind',
          name: '数据源类型',
          namespace: 'bms',
          version: 1,
          items: [
            { value: 'quota', label: '配额投影', label_key: '', color: '', disabled: false, sort: 30 },
          ],
        },
      ],
    })

    const index = await fetchOptionSetIndex(['bms.datasource.kind'])

    expect(mockedGet).toHaveBeenCalledWith('platform', '/option-sets', { keys: 'bms.datasource.kind' })
    expect(index['bms.datasource.kind']).toEqual([{ value: 'quota', label: '配额投影', sort: 30 }])
  })
})
