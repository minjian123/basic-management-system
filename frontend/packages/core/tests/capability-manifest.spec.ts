/** 能力依赖登记表与校验用例（02-3）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { BaseError, CAPABILITY_MANIFEST, assertCapabilityGraph, configureBase, resetBaseSinks, validateCapabilityGraph } from '../src'

afterEach(() => resetBaseSinks())

describe('validateCapabilityGraph', () => {
  it('内置登记表合规', () => {
    expect(validateCapabilityGraph(CAPABILITY_MANIFEST)).toEqual([])
    expect(CAPABILITY_MANIFEST.field).toEqual(['value'])
    expect(CAPABILITY_MANIFEST.validatable).toEqual(['labeled'])
  })

  it('依赖未登记', () => {
    const problems = validateCapabilityGraph({ a: ['missing'] })
    expect(problems).toHaveLength(1)
    expect(problems[0]?.kind).toBe('unregistered')
  })

  it('依赖成环', () => {
    const problems = validateCapabilityGraph({ a: ['b'], b: ['a'] })
    expect(problems.some((p) => p.kind === 'cycle')).toBe(true)
  })

  it('键名非法', () => {
    const problems = validateCapabilityGraph({ Bad_Key: [] })
    expect(problems.some((p) => p.kind === 'bad-key')).toBe(true)
  })
})

describe('assertCapabilityGraph', () => {
  it('开发态告警（不抛）', () => {
    const logger = vi.fn()
    configureBase({ logger })
    const problems = assertCapabilityGraph({ a: ['missing'] })
    expect(problems).toHaveLength(1)
    expect(logger).toHaveBeenCalled()
  })

  it('strict 抛 BaseError(10001)', () => {
    try {
      assertCapabilityGraph({ a: ['missing'] }, { strict: true })
      throw new Error('should throw')
    } catch (error) {
      expect(error).toBeInstanceOf(BaseError)
      expect((error as BaseError).code).toBe(10001)
    }
  })
})
