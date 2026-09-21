/** 模块契约与本地入口解析器用例（10_01；解析器口径随 02_01 由「本地加载器」收敛而来）。 */

import { describe, expect, it } from 'vitest'

import {
  BaseError,
  ErrorCodes,
  createModuleEntryTableResolver,
  defineModule,
  type ModuleEntryTable,
  type ModuleManifestEntry,
} from '../src'

const demo = defineModule({
  manifest: { name: 'demo', version: '0.1.0' },
  setup: () => ({ routes: [{ path: '/demo', name: 'DemoHome', component: async () => ({}) }] }),
})

const entry: ModuleManifestEntry = { name: 'demo', entry: 'demo', version: '0.1.0', mode: 'local' }

describe('defineModule', () => {
  it('校验模块名与版本并冻结', () => {
    expect(demo.manifest.name).toBe('demo')
    expect(Object.isFrozen(demo)).toBe(true)

    expect(() => defineModule({ manifest: { name: 'Demo_1', version: '1' }, setup: () => ({}) })).toThrow(BaseError)
    expect(() => defineModule({ manifest: { name: 'demo', version: ' ' }, setup: () => ({}) })).toThrow(BaseError)
  })
})

describe('createModuleEntryTableResolver（本地形态入口解析器）', () => {
  it('入口标识命中时返回入口模块（懒加载表按次调用）', async () => {
    let calls = 0
    const table: ModuleEntryTable = {
      demo: async () => {
        calls += 1
        return { default: demo }
      },
    }
    const resolve = createModuleEntryTableResolver(table)

    await expect(resolve(entry)).resolves.toEqual({ default: demo })
    await resolve(entry)
    expect(calls).toBe(2)
  })

  it('入口标识未登记报未注册不可用', async () => {
    const resolve = createModuleEntryTableResolver({})
    await expect(resolve(entry)).rejects.toMatchObject({ code: ErrorCodes.PROVIDER_NOT_REGISTERED })
  })
})
