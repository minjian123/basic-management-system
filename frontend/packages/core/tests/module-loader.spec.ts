// kiwi_id: 977
/** 清单驱动加载器用例（同接口换实现通路：清单即唯一来源，校验不过即拒绝加载）。 */

import { describe, expect, it } from 'vitest'

import { BaseError, LocalModuleLoader, ManifestModuleLoader, defineModule, type ModuleEntryTable } from '../src'

const demo = defineModule({
  manifest: { name: 'demo', version: '0.1.0' },
  setup: () => ({ routes: [{ path: '/demo', name: 'DemoHome', component: async () => ({}) }] }),
})

const entries = [{ name: 'demo', entry: 'demo', version: '0.1.0' }]

const table: ModuleEntryTable = {
  demo: async () => ({ default: demo }),
}

describe('ManifestModuleLoader（Kiwi 977）', () => {
  it('按清单加载：清单名 / 入口标识补入 manifest，注册声明透传', async () => {
    const loader = new ManifestModuleLoader(entries, table)
    const loaded = await loader.load('demo')

    expect(loaded.manifest).toEqual({ name: 'demo', version: '0.1.0', entry: 'demo' })
    expect(loaded.registration.routes?.map((route) => route.path)).toEqual(['/demo'])
    expect(loader.names()).toEqual(['demo'])
    expect(loader.entryOf('demo')?.entry).toBe('demo')
  })

  it('上下文注入前冻结为只读快照（模块读到冻结对象）', async () => {
    let frozen: boolean | undefined
    const loader = new ManifestModuleLoader(entries, {
      demo: async () => ({
        default: defineModule({
          manifest: { name: 'demo', version: '0.1.0' },
          setup: (context) => {
            frozen = Object.isFrozen(context)
            return { components: { 'demo:user': context.user, 'demo:tenant': context.tenant } }
          },
        }),
      }),
    })

    const loaded = await loader.load('demo', { user: 'alice' })

    expect(frozen).toBe(true)
    expect(loaded.registration.components).toEqual({ 'demo:user': 'alice', 'demo:tenant': undefined })
  })

  it('清单未登记名 / 入口未登记 一律拒绝加载', async () => {
    const loader = new ManifestModuleLoader(entries, table)
    await expect(loader.load('missing')).rejects.toBeInstanceOf(BaseError)
    await expect(new ManifestModuleLoader(entries, {}).load('demo')).rejects.toBeInstanceOf(BaseError)
  })

  it('入口缺默认导出 / 非模块定义形状 拒绝加载', async () => {
    await expect(new ManifestModuleLoader(entries, { demo: async () => ({}) }).load('demo')).rejects.toBeInstanceOf(
      BaseError,
    )
    await expect(
      new ManifestModuleLoader(entries, { demo: async () => ({ default: { manifest: { name: 'demo' } } }) }).load('demo'),
    ).rejects.toBeInstanceOf(BaseError)
  })

  it('模块自报名称 / 版本与清单不一致 拒绝加载（发布错位）', async () => {
    const otherName = defineModule({ manifest: { name: 'other', version: '0.1.0' }, setup: () => ({}) })
    const otherVersion = defineModule({ manifest: { name: 'demo', version: '9.9.9' }, setup: () => ({}) })

    await expect(new ManifestModuleLoader(entries, { demo: async () => ({ default: otherName }) }).load('demo')).rejects.toThrow(
      /模块名与清单不一致/,
    )
    await expect(
      new ManifestModuleLoader(entries, { demo: async () => ({ default: otherVersion }) }).load('demo'),
    ).rejects.toThrow(/模块版本与清单不一致/)
  })

  it('挂载 / 卸载幂等、重复挂载拒重、已挂载可读', async () => {
    const loader = new ManifestModuleLoader(entries, table)
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
    expect(loader.mountedNames()).toEqual([])
  })

  it('与本地实现同接口（同调用序列同结果）', async () => {
    const local = new LocalModuleLoader([demo])
    const manifest = new ManifestModuleLoader(entries, table)

    for (const loader of [local, manifest]) {
      const loaded = await loader.load('demo')
      loader.mount(loaded)
      expect(loader.mountedNames()).toEqual(['demo'])
      expect(loader.isMounted('demo')).toBe(true)
      loader.unmount('demo')
      expect(loader.isMounted('demo')).toBe(false)
      await expect(loader.load('missing')).rejects.toBeInstanceOf(BaseError)
    }
  })
})
