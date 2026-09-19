// kiwi_id: 769
/** 导出领域纯函数用例（08-5-1）：取数参数归一 / 选中集合 / 通路与决策 / 明文 / 文件名 / 错误文案。 */

import { describe, expect, it } from 'vitest'

import {
  canExportPlain,
  exportErrorMessage,
  exportFileName,
  normalizeExportParams,
  normalizeSelectedIds,
  resolveExportDecision,
  resolveExportMode,
} from '../src'

describe('取数参数归一', () => {
  it('剔除空值项且不改键名', () => {
    expect(
      normalizeExportParams({
        keyword: 'a',
        empty: '',
        blank: '   ',
        nil: undefined,
        none: null,
        list: [],
        keep: 0,
        order_by: 'created_at',
        order: 'desc',
      }),
    ).toEqual({ keyword: 'a', keep: 0, order_by: 'created_at', order: 'desc' })
    expect(normalizeExportParams()).toEqual({})
  })
})

describe('选中集合归一', () => {
  it('字符串化 + 去重 + 排序；空集合回落 undefined', () => {
    expect(normalizeSelectedIds([2, '1', '2'])).toEqual(['1', '2'])
    expect(normalizeSelectedIds([])).toBeUndefined()
    expect(normalizeSelectedIds()).toBeUndefined()
  })
})

describe('导出通路与决策', () => {
  it('阈值 0 不判断、超阈值转异步', () => {
    expect(resolveExportMode({ total: 1000, threshold: 0 })).toBe('sync')
    expect(resolveExportMode({ total: 1000, threshold: 500 })).toBe('async')
    expect(resolveExportMode({ total: 500, threshold: 500 })).toBe('sync')
    expect(resolveExportMode({})).toBe('sync')
  })

  it('明文需申请且持权限码', () => {
    expect(canExportPlain(true, true)).toBe(true)
    expect(canExportPlain(true, false)).toBe(false)
    expect(canExportPlain(false, true)).toBe(false)
  })

  it('决策顺序：未就绪 / 禁用 / 无权 / 未选中 / 无数据 / 允许', () => {
    expect(resolveExportDecision({ ready: false, total: 10 })).toEqual({ allowed: false, reason: 'degraded', mode: 'sync' })
    expect(resolveExportDecision({ ready: true, disabled: true, total: 10 }).reason).toBe('disabled')
    expect(resolveExportDecision({ ready: true, permAllowed: false, total: 10 }).reason).toBe('forbidden')
    expect(resolveExportDecision({ ready: true, scope: 'selected', selectedIds: [], total: 10 }).reason).toBe('no-selection')
    expect(resolveExportDecision({ ready: true, total: 0 })).toEqual({ allowed: false, reason: 'empty', mode: 'sync' })
    expect(resolveExportDecision({ ready: true, total: 10 })).toEqual({ allowed: true, mode: 'sync' })
    expect(resolveExportDecision({ ready: true, total: 10, threshold: 5 })).toEqual({ allowed: true, mode: 'async' })
  })

  it('选中导出且已选行时允许', () => {
    expect(resolveExportDecision({ ready: true, scope: 'selected', selectedIds: ['1'], total: 10 }).allowed).toBe(true)
  })
})

describe('文件名与错误文案', () => {
  it('文件名含前缀与紧凑时间戳', () => {
    expect(exportFileName('用户', new Date(2026, 8, 19, 10, 20, 30))).toBe('用户-20260919102030.xlsx')
  })

  it('错误文案：无权限 / 服务段 / 兜底', () => {
    expect(exportErrorMessage(403)).toBe('无导出权限')
    expect(exportErrorMessage(51001)).toBe('导出失败，请稍后重试')
    expect(exportErrorMessage(51001, '限流，请稍后重试')).toBe('限流，请稍后重试')
    expect(exportErrorMessage(undefined, '导出失败')).toBe('导出失败')
  })
})
