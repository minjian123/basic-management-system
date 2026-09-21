// kiwi_id: 977
/** 模块清单获取用例（宿主侧：获取失败按空清单继续，不阻塞启动）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { clearModuleError, useModuleError } from '@/module/boundary'
import { installModules } from '@/module/host'
import { loadModuleManifest } from '@/module/manifest'

/** 以给定响应 stub 全局 fetch。 */
function stubResponse(payload: unknown, ok = true, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok, status, json: async () => payload })),
  )
}

afterEach(() => {
  clearModuleError()
  vi.unstubAllGlobals()
})

describe('loadModuleManifest（Kiwi 977）', () => {
  it('成功获取：可用项与拒收项分离（形态缺省归一为 local）', async () => {
    stubResponse([
      { name: 'demo', entry: 'demo', version: '0.1.0' },
      { name: 'bad', entry: 'bad' },
    ])
    const result = await loadModuleManifest()

    expect(result.entries).toEqual([{ name: 'demo', entry: 'demo', version: '0.1.0', mode: 'local', enabled: true }])
    expect(result.rejected).toEqual([{ name: 'bad', reason: '版本缺失' }])
    expect(result.reason).toBeUndefined()
  })

  it('远端形态条目按绝对入口 URL 通过、相对路径被拒', async () => {
    stubResponse([
      { name: 'demo', entry: 'http://localhost:5002/remoteEntry.js', version: '0.1.0', mode: 'remote' },
      { name: 'relative', entry: '/modules/demo/remoteEntry.js', version: '1.0.0', mode: 'remote' },
    ])
    const result = await loadModuleManifest()

    expect(result.entries).toEqual([
      { name: 'demo', entry: 'http://localhost:5002/remoteEntry.js', version: '0.1.0', mode: 'remote', enabled: true },
    ])
    expect(result.rejected).toEqual([
      { name: 'relative', reason: '远端入口须为绝对 URL：/modules/demo/remoteEntry.js' },
    ])
  })

  it('HTTP 失败 / 网络异常 / 非数组 均按空清单与原因返回', async () => {
    stubResponse([], false, 404)
    expect(await loadModuleManifest()).toMatchObject({ entries: [], reason: '清单获取失败：HTTP 404' })

    stubResponse({ modules: [] })
    const notArray = await loadModuleManifest()
    expect(notArray.entries).toEqual([])
    expect(notArray.reason).toContain('清单获取失败：')

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down')
      }),
    )
    const broken = await loadModuleManifest()
    expect(broken.entries).toEqual([])
    expect(broken.reason).toContain('network down')

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw 'offline'
      }),
    )
    const thrown = await loadModuleManifest()
    expect(thrown.reason).toContain('offline')
  })

  it('获取失败不阻塞启动：空清单 + 错误状态', async () => {
    stubResponse([], false, 500)
    const summary = await installModules({})

    expect(summary).toEqual({ mounted: [], disabled: [], failures: [] })
    expect(useModuleError().value).toMatchObject({ module: 'modules.json' })
  })
})
