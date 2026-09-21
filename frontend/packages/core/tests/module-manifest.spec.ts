// kiwi_id: 977
/** 模块清单契约用例（清单驱动加载前置：严格三字段与逐项拒绝）。 */

import { describe, expect, it } from 'vitest'

import { BaseError, parseModuleManifest } from '../src'

describe('parseModuleManifest（Kiwi 977）', () => {
  it('三字段齐全时按清单序返回（忽略额外字段）', () => {
    const result = parseModuleManifest([
      { name: 'demo', entry: 'demo', version: '0.1.0' },
      { name: 'biz', entry: 'biz', version: '1.2.3', extra: 'ignored' },
    ])

    expect(result.entries).toEqual([
      { name: 'demo', entry: 'demo', version: '0.1.0' },
      { name: 'biz', entry: 'biz', version: '1.2.3' },
    ])
    expect(result.rejected).toEqual([])
  })

  it('缺字段 / 名非法逐项拒绝（其余项不受影响）', () => {
    const result = parseModuleManifest([
      { name: 'demo', entry: 'demo' },
      { entry: 'no-name', version: '1' },
      { name: 'Bad_Name', entry: 'bad', version: '1' },
      { name: 'nostart', version: '1' },
      { name: 'empty-entry', entry: '   ', version: '1' },
      { name: 'demo', entry: 'demo2', version: '0.2.0' },
      { name: 'ok', entry: 'ok', version: '1' },
    ])

    // 前一条 `demo` 因缺版本被拒，故其后同名的合法项可正常入选（逐项拒绝、互不影响）
    expect(result.entries).toEqual([
      { name: 'demo', entry: 'demo2', version: '0.2.0' },
      { name: 'ok', entry: 'ok', version: '1' },
    ])
    expect(result.rejected).toEqual([
      { name: 'demo', reason: '版本缺失' },
      { name: '', reason: '模块名缺失或非法：' },
      { name: 'Bad_Name', reason: '模块名缺失或非法：Bad_Name' },
      { name: 'nostart', reason: '入口缺失' },
      { name: 'empty-entry', reason: '入口缺失' },
    ])
  })

  it('重名拒收（保留先通过项）', () => {
    const result = parseModuleManifest([
      { name: 'demo', entry: 'demo', version: '0.1.0' },
      { name: 'demo', entry: 'demo2', version: '0.2.0' },
    ])

    expect(result.entries).toEqual([{ name: 'demo', entry: 'demo', version: '0.1.0' }])
    expect(result.rejected).toEqual([{ name: 'demo', reason: '清单内重名' }])
  })

  it('整份形态非法（非数组）抛能力声明违规', () => {
    expect(() => parseModuleManifest({})).toThrow(BaseError)
    expect(() => parseModuleManifest(null)).toThrow(BaseError)
    expect(() => parseModuleManifest('demo')).toThrow(BaseError)
  })
})
