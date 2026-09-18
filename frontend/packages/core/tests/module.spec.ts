/** 模块契约与本地加载器用例（10_01）。 */

import { describe, expect, it } from 'vitest'

import { BaseError, LocalModuleLoader, defineModule } from '../src'

const demo = defineModule({
  manifest: { name: 'demo', version: '0.1.0' },
  setup: () => ({ routes: [{ path: '/demo', name: 'DemoHome', component: async () => ({}) }] }),
})

describe('defineModule', () => {
  it('校验模块名与版本并冻结', () => {
    expect(demo.manifest.name).toBe('demo')
    expect(Object.isFrozen(demo)).toBe(true)

    expect(() => defineModule({ manifest: { name: 'Demo_1', version: '1' }, setup: () => ({}) })).toThrow(BaseError)
    expect(() => defineModule({ manifest: { name: 'demo', version: ' ' }, setup: () => ({}) })).toThrow(BaseError)
  })
})

describe('LocalModuleLoader', () => {
  it('加载并返回注册声明（透传宿主上下文）', async () => {
    const loader = new LocalModuleLoader([
      defineModule({
        manifest: { name: 'ctx', version: '1' },
        setup: (context) => ({ cards: [context.user] }),
      }),
    ])
    const loaded = await loader.load('ctx', { user: 'alice' })
    expect(loaded.registration.cards).toEqual(['alice'])
  })

  it('未登记模块加载报未注册不可用', async () => {
    const loader = new LocalModuleLoader()
    await expect(loader.load('missing')).rejects.toBeInstanceOf(BaseError)
  })

  it('挂载 / 卸载幂等与重复挂载拒重', async () => {
    const loader = new LocalModuleLoader([demo])
    const loaded = await loader.load('demo')
    expect(loader.isMounted('demo')).toBe(false)

    loader.mount(loaded)
    expect(loader.isMounted('demo')).toBe(true)
    expect(loader.mountedNames()).toEqual(['demo'])
    expect(loader.getMounted('demo')).toBe(loaded)
    expect(() => loader.mount(loaded)).toThrow(BaseError)

    loader.unmount('demo')
    loader.unmount('demo')
    expect(loader.isMounted('demo')).toBe(false)
  })

  it('同名模块登记拒重', () => {
    const loader = new LocalModuleLoader()
    loader.register(demo)
    expect(() => loader.register(demo)).toThrow(BaseError)
  })
})
