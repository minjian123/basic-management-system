/** 租户管理文案映射用例（04_01）：状态 / 模块状态 / 配额维度与单位全覆盖。 */
// kiwi_id: 2325

import { describe, expect, it } from 'vitest'

import {
  MODULE_STATUS_OPTIONS,
  TENANT_STATUS_OPTIONS,
  moduleStatusLabel,
  quotaLabel,
  quotaUnit,
  tenantStatusLabel,
  tenantStatusTag,
} from '@/views/system/tenant/labels'

describe('租户文案映射（04_01）', () => {
  it('租户状态：选项 / 文案 / 标签类型', () => {
    expect(TENANT_STATUS_OPTIONS.map((item) => item.value)).toEqual(['provisioning', 'active', 'suspended'])
    expect(tenantStatusLabel('provisioning')).toBe('开通中')
    expect(tenantStatusLabel('suspended')).toBe('停用')
    expect(tenantStatusLabel('active')).toBe('启用')
    expect(tenantStatusLabel(undefined)).toBe('启用')
    expect(tenantStatusTag('provisioning')).toBe('warning')
    expect(tenantStatusTag('suspended')).toBe('info')
    expect(tenantStatusTag('active')).toBe('success')
  })

  it('模块状态：选项 / 文案三态', () => {
    expect(MODULE_STATUS_OPTIONS.map((item) => item.value)).toEqual(['enabled', 'disabled', 'not_opened'])
    expect(moduleStatusLabel('enabled')).toBe('已启用')
    expect(moduleStatusLabel('disabled')).toBe('已停用')
    expect(moduleStatusLabel('not_opened')).toBe('未开通')
    expect(moduleStatusLabel(undefined)).toBe('未开通')
  })

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
