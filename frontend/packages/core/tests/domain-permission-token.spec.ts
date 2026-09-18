/** 权限判定与令牌解析用例（02-6）。 */

import { describe, expect, it } from 'vitest'

import { evaluatePermission, resolveToken } from '../src'

describe('evaluatePermission', () => {
  it('任一 / 全部 / 取反', () => {
    const codes = ['user:read', 'user:write']
    expect(evaluatePermission(codes, ['user:read'])).toBe(true)
    expect(evaluatePermission(codes, ['user:read', 'user:delete'], 'any')).toBe(true)
    expect(evaluatePermission(codes, ['user:read', 'user:delete'], 'all')).toBe(false)
    expect(evaluatePermission(codes, ['user:delete'], 'not')).toBe(true)
    expect(evaluatePermission(codes, ['user:read'], 'not')).toBe(false)
  })

  it('空要求：any=false / all=true / not=true', () => {
    const codes: string[] = []
    expect(evaluatePermission(codes, [], 'any')).toBe(false)
    expect(evaluatePermission(codes, [], 'all')).toBe(true)
    expect(evaluatePermission(codes, [], 'not')).toBe(true)
  })
})

describe('resolveToken', () => {
  it('按路径解析令牌值', () => {
    const tokens = { spacing: { sm: '4px' }, breakpoints: { md: 768 } }
    expect(resolveToken(tokens, 'spacing.sm')).toBe('4px')
    expect(resolveToken(tokens, 'breakpoints.md')).toBe(768)
    expect(resolveToken(tokens, 'spacing.missing')).toBeUndefined()
    expect(resolveToken(tokens, 'colors.primary')).toBeUndefined()
  })
})
