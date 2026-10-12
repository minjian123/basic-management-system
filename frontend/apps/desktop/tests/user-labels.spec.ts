/** 用户管理 / 账号锁定页文案映射用例（02_02 / Kiwi 2277）：状态、锁定类型、解锁方式与时间展示。 */
// kiwi_id: 2277

import { describe, expect, it } from 'vitest'

import {
  LOCK_TYPE_OPTIONS,
  UNLOCK_STATE_OPTIONS,
  USER_STATUS_OPTIONS,
  formatDateTime,
  lockTypeLabel,
  lockTypeTag,
  unlockModeLabel,
  userStatusLabel,
} from '@/views/system/user/labels'

describe('用户状态文案（02_02）', () => {
  it('状态下拉选项与文案映射', () => {
    expect(USER_STATUS_OPTIONS).toEqual([
      { label: '启用', value: 'enabled' },
      { label: '停用', value: 'disabled' },
    ])
    expect(userStatusLabel('enabled')).toBe('启用')
    expect(userStatusLabel('disabled')).toBe('停用')
    // 缺省 / 未知取值一律按启用展示
    expect(userStatusLabel(undefined)).toBe('启用')
    expect(userStatusLabel('other')).toBe('启用')
  })
})

describe('锁定类型文案与标签类型（02_02）', () => {
  it('筛选项齐备', () => {
    expect(LOCK_TYPE_OPTIONS.map((item) => item.value)).toEqual(['fail_limit', 'inactive', 'manual'])
    expect(UNLOCK_STATE_OPTIONS.map((item) => item.value)).toEqual(['open', 'done'])
  })

  it('三类锁定类型命中映射；未知取值原样回显', () => {
    expect(lockTypeLabel('fail_limit')).toBe('登录失败超限')
    expect(lockTypeLabel('inactive')).toBe('长期未登录')
    expect(lockTypeLabel('manual')).toBe('手动锁定')
    expect(lockTypeLabel('other')).toBe('other')
  })

  it('标签类型三类命中；未知取值回落 info', () => {
    expect(lockTypeTag('fail_limit')).toBe('warning')
    expect(lockTypeTag('inactive')).toBe('danger')
    expect(lockTypeTag('manual')).toBe('info')
    expect(lockTypeTag('other')).toBe('info')
  })
})

describe('时间展示（02_02）', () => {
  it('UTC ISO 归一为 `YYYY-MM-DD HH:mm:ss`', () => {
    expect(formatDateTime('2026-01-02T03:04:05Z')).toBe('2026-01-02 03:04:05')
    expect(formatDateTime('2026-01-02T03:04:05.123+08:00')).toBe('2026-01-02 03:04:05')
  })

  it('空值（null / undefined / 空串）显示占位符', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined)).toBe('—')
    expect(formatDateTime('')).toBe('—')
  })
})

describe('解锁方式文案（02_02）', () => {
  it('手动 / 自动两态与未解锁占位', () => {
    expect(unlockModeLabel('manual')).toBe('手动解锁')
    expect(unlockModeLabel('auto')).toBe('自动解锁')
    expect(unlockModeLabel(null)).toBe('—')
    expect(unlockModeLabel(undefined)).toBe('—')
    expect(unlockModeLabel('other')).toBe('—')
  })
})
