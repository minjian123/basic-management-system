// kiwi_id: 977
/** 清单驱动加载器用例（清单即唯一来源；入口来源由解析器注入，本地与远端同接口同校验链）。 */

import { describe, expect, it } from 'vitest'

import {
  BaseError,
  ManifestModuleLoader,
  MODULE_CONTRACT_VERSION,
  MODULE_EXPOSE_KEY,
  MODULE_LOAD_TIMEOUT_MS,
  MODULE_REMOTE_ENTRY_FILE,
  createModuleEntryTableResolver,
  defineModule,
  remoteEntryUrl,
  type ModuleEntryResolver,
  type ModuleEntryTable,
  type ModuleLoadObserver,
  type ModuleManifestEntry,
} from '../src'

const demo = defineModule({
  manifest: { name: 'demo', version: '0.1.0', contractVersion: MODULE_CONTRACT_VERSION },
  setup: () => ({ routes: [{ path: '/demo', name: 'DemoHome', component: async () => ({}) }] }),
})

const entries: ModuleManifestEntry[] = [
  { name: 'demo', entry: 'demo', version: '0.1.0', mode: 'local', enabled: true },
]

const table: ModuleEntryTable = {
  demo: async () => ({ default: demo }),
}

const local = createModuleEntryTableResolver(table)

describe('ManifestModuleLoader（Kiwi 977 / 978）', () => {
  it('按清单加载：清单名 / 入口标识补入 manifest，注册声明透传', async () => {
    const loader = new ManifestModuleLoader(entries, local)
    const loaded = await loader.load('demo')

    expect(loaded.manifest).toEqual({
      name: 'demo',
      version: '0.1.0',
      entry: 'demo',
      contractVersion: MODULE_CONTRACT_VERSION,
    })
    expect(loaded.registration.routes?.map((route) => route.path)).toEqual(['/demo'])
    expect(loader.names()).toEqual(['demo'])
    expect(loader.entryOf('demo')?.entry).toBe('demo')
  })

  it('上下文注入前冻结为只读快照（模块读到冻结对象）', async () => {
    let frozen: boolean | undefined
    const loader = new ManifestModuleLoader(entries, async () => ({
      default: defineModule({
        manifest: { name: 'demo', version: '0.1.0', contractVersion: MODULE_CONTRACT_VERSION },
        setup: (context) => {
          frozen = Object.isFrozen(context)
          return { components: { 'demo:user': context.user, 'demo:tenant': context.tenant } }
        },
      }),
    }))

    const loaded = await loader.load('demo', { user: 'alice' })

    expect(frozen).toBe(true)
    expect(loaded.registration.components).toEqual({ 'demo:user': 'alice', 'demo:tenant': undefined })
  })

  it('清单未登记名 拒绝加载（未注册不可用）', async () => {
    const loader = new ManifestModuleLoader(entries, local)
    await expect(loader.load('missing')).rejects.toBeInstanceOf(BaseError)
  })

  it('本地入口标识未登记 拒绝加载（入口解析器落此判定）', async () => {
    const loader = new ManifestModuleLoader(entries, createModuleEntryTableResolver({}))
    await expect(loader.load('demo')).rejects.toThrow(/模块入口未登记/)
  })

  it('解析器抛错原样上抛（远端不可达 / 未暴露不吞错、不自造错误）', async () => {
    const failing: ModuleEntryResolver = async () => {
      throw new Error('远端入口加载失败：HTTP 404')
    }
    const loader = new ManifestModuleLoader(
      [{ name: 'demo', entry: 'http://localhost:5002/remoteEntry.js', version: '0.1.0', mode: 'remote', enabled: true }],
      failing,
    )

    await expect(loader.load('demo')).rejects.toThrow(/远端入口加载失败/)
  })

  it('入口缺默认导出 / 非模块定义形状 拒绝加载', async () => {
    await expect(new ManifestModuleLoader(entries, async () => ({})).load('demo')).rejects.toBeInstanceOf(BaseError)
    await expect(
      new ManifestModuleLoader(entries, async () => ({ default: { manifest: { name: 'demo' } } })).load('demo'),
    ).rejects.toBeInstanceOf(BaseError)
  })

  it('模块自报名称 / 版本与清单不一致 拒绝加载（发布错位）', async () => {
    const otherName = defineModule({
      manifest: { name: 'other', version: '0.1.0', contractVersion: MODULE_CONTRACT_VERSION },
      setup: () => ({}),
    })
    const otherVersion = defineModule({
      manifest: { name: 'demo', version: '9.9.9', contractVersion: MODULE_CONTRACT_VERSION },
      setup: () => ({}),
    })

    await expect(new ManifestModuleLoader(entries, async () => ({ default: otherName })).load('demo')).rejects.toThrow(
      /模块名与清单不一致/,
    )
    await expect(
      new ManifestModuleLoader(entries, async () => ({ default: otherVersion })).load('demo'),
    ).rejects.toThrow(/模块版本与清单不一致/)
  })

  it('停用项（enabled: false）不进可见集且拒绝加载（清单内停用保留入口与版本）', async () => {
    const disabledEntries: ModuleManifestEntry[] = [
      { name: 'demo', entry: 'demo', version: '0.1.0', mode: 'local', enabled: false },
    ]
    const loader = new ManifestModuleLoader(disabledEntries, local)

    expect(loader.names()).toEqual([])
    await expect(loader.load('demo')).rejects.toThrow(/模块不可见（清单 enabled=false）/)
  })

  it('契约版本不匹配 拒绝加载（契约升级须模块适配后重新构建）', async () => {
    const stale = defineModule({
      manifest: { name: 'demo', version: '0.1.0', contractVersion: MODULE_CONTRACT_VERSION + 1 },
      setup: () => ({}),
    })
    const loader = new ManifestModuleLoader(entries, async () => ({ default: stale }))

    await expect(loader.load('demo')).rejects.toThrow(/模块契约版本不匹配/)
  })

  it('入口契约版本缺失 / 非数字 视同非模块定义（形状校验拒绝）', async () => {
    const loader = new ManifestModuleLoader(entries, async () => ({
      default: { manifest: { name: 'demo', version: '0.1.0' }, setup: () => ({}) },
    }))

    await expect(loader.load('demo')).rejects.toThrow(/未默认导出模块定义/)
  })

  it('挂载 / 卸载幂等、重复挂载拒重、已挂载可读', async () => {
    const loader = new ManifestModuleLoader(entries, local)
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

  it('同一加载器承接本地与远端两类解析器：调用序列同结果（入口通路可换、接口与校验不变）', async () => {
    const remote: ModuleEntryResolver = async () => ({ default: demo })
    const loader = new ManifestModuleLoader(entries, local)
    const remoteLoader = new ManifestModuleLoader(entries, remote)

    for (const item of [loader, remoteLoader]) {
      const loaded = await item.load('demo')
      item.mount(loaded)
      expect(item.mountedNames()).toEqual(['demo'])
      expect(item.isMounted('demo')).toBe(true)
      item.unmount('demo')
      expect(item.isMounted('demo')).toBe(false)
      await expect(item.load('missing')).rejects.toBeInstanceOf(BaseError)
    }
  })

  it('远端入口约定常量与 URL 拼接成文', () => {
    expect(MODULE_REMOTE_ENTRY_FILE).toBe('remoteEntry.js')
    expect(MODULE_EXPOSE_KEY).toBe('module')
    expect(MODULE_LOAD_TIMEOUT_MS).toBe(10_000)
    expect(remoteEntryUrl('http://localhost:5002/')).toBe('http://localhost:5002/remoteEntry.js')
    expect(remoteEntryUrl('https://cdn.example.com/demo')).toBe('https://cdn.example.com/demo/remoteEntry.js')
  })

  it('观测钩子：resolve / setup 阶段各自计时与成败标注（Kiwi 982）', async () => {
    const phases: { phase: string; ok: boolean; durationMs: number }[] = []
    const observer: ModuleLoadObserver = {
      onPhase(_name, _version, phase, durationMs, ok) {
        phases.push({ phase, ok, durationMs })
      },
    }
    const loader = new ManifestModuleLoader(entries, local, { observer })

    await loader.load('demo')

    expect(phases.map((item) => `${item.phase}:${String(item.ok)}`)).toEqual(['resolve:true', 'setup:true'])
    expect(phases.every((item) => item.durationMs >= 0)).toBe(true)
  })

  it('加载超时：整个 load() 计时，超时拒绝且原因明示（原 Promise 结果被吞）（Kiwi 982）', async () => {
    const loader = new ManifestModuleLoader(entries, () => new Promise(() => {}), { timeoutMs: 5 })

    await expect(loader.load('demo')).rejects.toThrow(/模块加载超时（>5ms）/)
  })

  it('setup 抛错：观测钩子记 setup 失败并原样上抛（Kiwi 982）', async () => {
    const phases: { phase: string; ok: boolean }[] = []
    const observer: ModuleLoadObserver = {
      onPhase(_name, _version, phase, _durationMs, ok) {
        phases.push({ phase, ok })
      },
    }
    const failing = defineModule({
      manifest: { name: 'demo', version: '0.1.0', contractVersion: MODULE_CONTRACT_VERSION },
      setup: () => {
        throw new Error('初始化失败')
      },
    })
    const loader = new ManifestModuleLoader(entries, async () => ({ default: failing }), { observer })

    await expect(loader.load('demo')).rejects.toThrow(/初始化失败/)
    expect(phases).toEqual([
      { phase: 'resolve', ok: true },
      { phase: 'setup', ok: false },
    ])
  })
})
