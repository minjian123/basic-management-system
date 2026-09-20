/** 领域纯函数：状态语义色（三层取色 / 内置映射 / 固定色 / 令牌名）+ 状态契约套件。 */

import { describeStatusContract, type StatusContractTarget } from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

import {
  STATUS_BULLET_SIZE,
  STATUS_BUILTIN_MAP,
  STATUS_FALLBACK_SEMANTIC,
  STATUS_FIXED_MAP,
  STATUS_SEMANTICS,
  STATUS_SEMANTIC_TOKENS,
  describeStatus,
  isStatusSemantic,
  normalizeStatusColorMap,
  normalizeStatusValue,
  resolveStatusSemantic,
  resolveStatusText,
  statusTokenOf,
} from '../src'

/** 契约目标：状态语义色领域纯函数。 */
const statusTarget: StatusContractTarget = {
  describe: (value, options) => describeStatus(value, options),
}

describeStatusContract('状态语义色契约（describeStatus）', () => statusTarget)

describe('状态归一', () => {
  it('字符串去空格转小写，布尔映射语义键', () => {
    expect(normalizeStatusValue(' Enabled ')).toBe('enabled')
    expect(normalizeStatusValue(true)).toBe('success')
    expect(normalizeStatusValue(false)).toBe('info')
    expect(normalizeStatusValue(null)).toBe('')
    expect(normalizeStatusValue(1)).toBe('1')
  })

  it('合法语义色判定与映射归一', () => {
    expect(isStatusSemantic('danger')).toBe(true)
    expect(isStatusSemantic('DANGER')).toBe(false)
    expect(isStatusSemantic(1)).toBe(false)
    expect(normalizeStatusColorMap({ a: 'danger', b: 'bad', c: 1 })).toEqual({ a: 'danger' })
    expect(normalizeStatusColorMap(null)).toEqual({})
    expect(normalizeStatusColorMap(['danger'])).toEqual({})
  })
})

describe('取色三层优先级', () => {
  it('显式 > 数据源色 > 字段映射 > 内置 > 兜底', () => {
    expect(resolveStatusSemantic({ value: 'enabled', semantic: 'primary' })).toBe('primary')
    expect(resolveStatusSemantic({ value: 'enabled', sourceColor: 'danger' })).toBe('danger')
    expect(resolveStatusSemantic({ value: 'custom', colorMap: { custom: 'warning' } })).toBe('warning')
    expect(resolveStatusSemantic({ value: 'enabled' })).toBe('success')
    expect(resolveStatusSemantic({ value: 'unknown' })).toBe(STATUS_FALLBACK_SEMANTIC)
    expect(resolveStatusSemantic({})).toBe(STATUS_FALLBACK_SEMANTIC)
  })

  it('非法来源色 / 映射值回落下一层', () => {
    expect(resolveStatusSemantic({ value: 'enabled', sourceColor: '#f00' })).toBe('success')
    expect(resolveStatusSemantic({ value: 'enabled', colorMap: { enabled: '#f00' } })).toBe('success')
    expect(resolveStatusSemantic({ value: 'enabled', sourceColor: '#f00', colorMap: { enabled: 'warning' } })).toBe(
      'warning',
    )
  })

  it('布尔与固定状态色', () => {
    expect(resolveStatusSemantic({ value: true })).toBe('success')
    expect(resolveStatusSemantic({ value: false })).toBe('info')
    expect(STATUS_FIXED_MAP['rejected']).toBe('danger')
    expect(STATUS_FIXED_MAP['pending']).toBe('warning')
    expect(STATUS_FIXED_MAP['approved']).toBe('success')
  })
})

describe('令牌与描述', () => {
  it('令牌名一律 --bms- 前缀且五档齐备', () => {
    expect(STATUS_SEMANTICS).toHaveLength(5)
    for (const semantic of STATUS_SEMANTICS) {
      expect(statusTokenOf(semantic).startsWith('--bms-')).toBe(true)
      expect(STATUS_SEMANTIC_TOKENS[semantic]).toBe(statusTokenOf(semantic))
    }
    expect(STATUS_BULLET_SIZE).toBe(8)
    expect(Object.keys(STATUS_BUILTIN_MAP).length).toBeGreaterThan(30)
  })

  it('描述含语义色 / 令牌 / 文案 / 已知性', () => {
    const known = describeStatus('enabled')
    expect(known).toEqual({ semantic: 'success', token: '--bms-color-success', text: 'enabled', known: true })

    const overridden = describeStatus('enabled', { text: '启用中' })
    expect(overridden.text).toBe('启用中')

    const unknown = describeStatus('未定义')
    expect(unknown).toMatchObject({ semantic: 'info', text: '未定义', known: false })

    const explicit = describeStatus('未定义', { semantic: 'primary' })
    expect(explicit).toMatchObject({ semantic: 'primary', known: true })

    expect(resolveStatusText(undefined, 5)).toBe('5')
    expect(resolveStatusText('', null)).toBe('')
  })
})
