/** 租户管理文案映射用例（04_01）：配额维度与单位（状态 / 模块状态已改由选项集快照提供）。 */
// kiwi_id: 2325

import { describe, expect, it } from 'vitest'

import { quotaLabel, quotaUnit } from '@/views/system/tenant/labels'

describe('租户配额文案映射（04_01）', () => {
  it('配额维度：文案与单位（存储 / 调用 / 其它）', () => {
    expect(quotaLabel('user_count')).toBe('用户数')
    expect(quotaLabel('storage_bytes')).toBe('存储空间')
    expect(quotaLabel('open_calls')).toBe('开放接口调用量')
    expect(quotaLabel('custom')).toBe('custom')
    expect(quotaUnit('storage_bytes')).toBe('字节')
    expect(quotaUnit('open_calls')).toBe('次')
    expect(quotaUnit('user_count')).toBe('个')
  })
})
