// kiwi_id: 977
/** 模块主题令牌机制用例（汇聚 / 应用 / 还原；核心不触 DOM，应用器由调用方注入）。 */

import { describe, expect, it } from 'vitest'

import {
  applyThemeTokens,
  collectThemeTokens,
  releaseThemeTokens,
  type ThemeTokenRecord,
  type ThemeTokenSource,
  type ThemeTokenTarget,
} from '../src'

/** 记录调用的假应用器（核心侧无 DOM，测试以记录代替）。 */
function createTarget(): ThemeTokenTarget & { calls: string[]; values: Record<string, string> } {
  const calls: string[] = []
  const values: Record<string, string> = {}
  return {
    calls,
    values,
    setToken: (name, value) => {
      calls.push(`set:${name}`)
      values[name] = value
    },
    removeToken: (name) => {
      calls.push(`remove:${name}`)
    },
  }
}

const records: ThemeTokenRecord[] = [
  { key: 'platform:default', tokens: { '--bms-color-primary': '#409eff', '--bms-color-bg': '#fff' }, mode: 'light' },
  { key: 'demo:brand', tokens: { '--bms-color-primary': '#3a7bd5' }, mode: 'brand' },
]

const source: ThemeTokenSource = {
  values: () => records,
  byMode: (mode: string) => records.filter((record) => record.mode === mode),
}

describe('主题令牌机制（Kiwi 977）', () => {
  it('按登记序汇聚（同令牌后者覆盖前者）', () => {
    expect(collectThemeTokens(source)).toEqual({ '--bms-color-primary': '#3a7bd5', '--bms-color-bg': '#fff' })
  })

  it('按模式汇聚（未提供筛选实现时取全部）', () => {
    expect(collectThemeTokens(source, { mode: 'brand' })).toEqual({ '--bms-color-primary': '#3a7bd5' })
    expect(collectThemeTokens({ values: source.values }, { mode: 'brand' })).toEqual({
      '--bms-color-primary': '#3a7bd5',
      '--bms-color-bg': '#fff',
    })
  })

  it('应用返回已写入令牌名，还原按名逆序移除且幂等', () => {
    const target = createTarget()
    const names = applyThemeTokens(target, { '--bms-a': '1', '--bms-b': '2' })

    expect(names).toEqual(['--bms-a', '--bms-b'])
    expect(target.calls).toEqual(['set:--bms-a', 'set:--bms-b'])
    expect(target.values).toEqual({ '--bms-a': '1', '--bms-b': '2' })

    releaseThemeTokens(target, names)
    releaseThemeTokens(target, names)
    expect(target.calls).toEqual(['set:--bms-a', 'set:--bms-b', 'remove:--bms-b', 'remove:--bms-a', 'remove:--bms-b', 'remove:--bms-a'])
  })
})
