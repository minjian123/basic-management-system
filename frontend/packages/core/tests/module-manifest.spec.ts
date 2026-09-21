// kiwi_id: 977
/** 模块清单契约用例（加载前置：三必填 + 一可选形态，严格校验与逐项拒绝）。 */

import { describe, expect, it } from 'vitest'

import { BaseError, parseModuleManifest } from '../src'

describe('parseModuleManifest（Kiwi 977 / 978）', () => {
  it('三字段齐全时按清单序返回，形态缺省归一为 local（忽略额外字段）', () => {
    const result = parseModuleManifest([
      { name: 'demo', entry: 'demo', version: '0.1.0' },
      { name: 'biz', entry: 'biz', version: '1.2.3', extra: 'ignored' },
    ])

    expect(result.entries).toEqual([
      { name: 'demo', entry: 'demo', version: '0.1.0', mode: 'local' },
      { name: 'biz', entry: 'biz', version: '1.2.3', mode: 'local' },
    ])
    expect(result.rejected).toEqual([])
  })

  it('形态显式给出时保留：remote 须配绝对入口 URL', () => {
    const result = parseModuleManifest([
      { name: 'demo', entry: 'http://localhost:5002/remoteEntry.js', version: '0.1.0', mode: 'remote' },
      { name: 'legacy', entry: 'legacy', version: '1.0.0', mode: 'local' },
    ])

    expect(result.entries).toEqual([
      { name: 'demo', entry: 'http://localhost:5002/remoteEntry.js', version: '0.1.0', mode: 'remote' },
      { name: 'legacy', entry: 'legacy', version: '1.0.0', mode: 'local' },
    ])
    expect(result.rejected).toEqual([])
  })

  it('形态非法 / remote 入口非绝对 URL 逐项拒绝（其余项不受影响）', () => {
    const result = parseModuleManifest([
      { name: 'bad-mode', entry: 'bad-mode', version: '1', mode: 'federation' },
      { name: 'relative', entry: '/modules/demo/remoteEntry.js', version: '1', mode: 'remote' },
      { name: 'bare', entry: 'demo', version: '1', mode: 'remote' },
      { name: 'ok', entry: 'https://cdn.example.com/demo/remoteEntry.js', version: '1', mode: 'remote' },
    ])

    expect(result.entries).toEqual([
      { name: 'ok', entry: 'https://cdn.example.com/demo/remoteEntry.js', version: '1', mode: 'remote' },
    ])
    expect(result.rejected).toEqual([
      { name: 'bad-mode', reason: '加载形态非法：federation' },
      { name: 'relative', reason: '远端入口须为绝对 URL：/modules/demo/remoteEntry.js' },
      { name: 'bare', reason: '远端入口须为绝对 URL：demo' },
    ])
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
      { name: 'demo', entry: 'demo2', version: '0.2.0', mode: 'local' },
      { name: 'ok', entry: 'ok', version: '1', mode: 'local' },
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

    expect(result.entries).toEqual([{ name: 'demo', entry: 'demo', version: '0.1.0', mode: 'local' }])
    expect(result.rejected).toEqual([{ name: 'demo', reason: '清单内重名' }])
  })

  it('整份形态非法（非数组）抛能力声明违规', () => {
    expect(() => parseModuleManifest({})).toThrow(BaseError)
    expect(() => parseModuleManifest(null)).toThrow(BaseError)
    expect(() => parseModuleManifest('demo')).toThrow(BaseError)
  })
})
