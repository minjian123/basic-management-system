// kiwi_id: 978
/** 远端入口解析器用例（Module Federation 运行时：按清单登记容器 → 按暴露键加载模块定义；不吞错、不自造错误）。 */

import { MODULE_EXPOSE_KEY, MODULE_REMOTE_ENTRY_FILE, remoteEntryUrl } from '@bms/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MODULE_REMOTE_ENTRY_TYPE, MODULE_REMOTE_ORIGIN, createFederationEntryResolver } from '@/module/federation'

import { demoDefinition, REMOTE_ENTRY } from './support/module-fixture'

/** Module Federation 运行时替身（浏览器侧运行时在测试环境不参与）。 */
const { registerRemotes, loadRemote } = vi.hoisted(() => ({ registerRemotes: vi.fn(), loadRemote: vi.fn() }))
vi.mock('@module-federation/runtime', () => ({ registerRemotes, loadRemote }))

beforeEach(() => {
  registerRemotes.mockReset()
  loadRemote.mockReset()
})

describe('createFederationEntryResolver（Kiwi 978）', () => {
  it('按清单条目登记远端容器（同名以清单为准重登记）并按暴露键加载', async () => {
    loadRemote.mockResolvedValue({ default: demoDefinition() })
    const resolve = createFederationEntryResolver()

    const loaded = await resolve(REMOTE_ENTRY)

    expect(registerRemotes).toHaveBeenCalledWith(
      [{ name: 'demo', entry: REMOTE_ENTRY.entry, type: MODULE_REMOTE_ENTRY_TYPE }],
      { force: true },
    )
    expect(MODULE_REMOTE_ENTRY_TYPE).toBe('module')
    expect(loadRemote).toHaveBeenCalledWith(`demo/${MODULE_EXPOSE_KEY}`)
    expect(loadRemote).toHaveBeenCalledWith('demo/module')
    expect((loaded.default as { manifest: { name: string } }).manifest.name).toBe('demo')
  })

  it('重复解析同一模块幂等（重登记覆盖、不新增契约）', async () => {
    loadRemote.mockResolvedValue({ default: demoDefinition() })
    const resolve = createFederationEntryResolver()

    await resolve(REMOTE_ENTRY)
    await resolve(REMOTE_ENTRY)

    expect(registerRemotes).toHaveBeenCalledTimes(2)
    for (const call of registerRemotes.mock.calls) {
      expect(call[1]).toEqual({ force: true })
    }
  })

  it('远端不可达 / 未暴露时错误原样上抛（不吞错、不自造错误码）', async () => {
    loadRemote.mockRejectedValue(new Error('远端入口加载失败：HTTP 404'))
    const resolve = createFederationEntryResolver()

    await expect(resolve(REMOTE_ENTRY)).rejects.toThrow(/远端入口加载失败/)
  })

  it('容器返回空时返回空模块对象（形状校验交由加载器统一判定）', async () => {
    loadRemote.mockResolvedValue(undefined)
    const resolve = createFederationEntryResolver()

    await expect(resolve(REMOTE_ENTRY)).resolves.toEqual({})
  })

  it('远端入口约定：容器名 = 清单名、入口文件名与暴露键以 core 常量成文、演示 origin 为本地端口', () => {
    expect(MODULE_REMOTE_ENTRY_FILE).toBe('remoteEntry.js')
    expect(MODULE_EXPOSE_KEY).toBe('module')
    expect(MODULE_REMOTE_ORIGIN).toBe('http://localhost:5002')
    expect(remoteEntryUrl(MODULE_REMOTE_ORIGIN)).toBe('http://localhost:5002/remoteEntry.js')
    expect(REMOTE_ENTRY.entry).toBe(remoteEntryUrl(MODULE_REMOTE_ORIGIN))
  })
})
