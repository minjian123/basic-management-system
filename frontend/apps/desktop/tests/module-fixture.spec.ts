/** 宿主模块用例共用夹具用例（05-04 / Kiwi 983）：清单条目形态与演示模块定义同形性直接断言。 */
// kiwi_id: 983

import { MODULE_CONTRACT_VERSION } from '@bms/core'
import { describe, expect, it } from 'vitest'

import { LOCAL_ENTRY, REMOTE_ENTRY, demoDefinition } from './support/module-fixture'

describe('模块夹具（Kiwi 983）', () => {
  it('远端条目：绝对入口 URL + `mode: remote`', () => {
    expect(REMOTE_ENTRY).toEqual({
      name: 'demo',
      entry: 'http://localhost:5002/demo/0.1.0/remoteEntry.js',
      version: '0.1.0',
      mode: 'remote',
      enabled: true,
    })
  })

  it('本地条目：入口为模块源码标识 + `mode: local`', () => {
    expect(LOCAL_ENTRY).toEqual({
      name: 'legacy',
      entry: 'legacy',
      version: '1.0.0',
      mode: 'local',
      enabled: true,
    })
  })

  it('每次调用返回新实例（避免用例间共享注册声明）', () => {
    expect(demoDefinition()).not.toBe(demoDefinition())
  })

  it('模块定义清单：名称 / 版本 / 契约版本与清单条目一致', () => {
    const definition = demoDefinition()
    expect(definition.manifest).toEqual({ name: 'demo', version: '0.1.0', contractVersion: MODULE_CONTRACT_VERSION })
    expect(definition.manifest.version).toBe(REMOTE_ENTRY.version)
    expect(definition.manifest.name).toBe(REMOTE_ENTRY.name)
  })

  it('装配声明：八类注册齐备且键带 `demo:` 前缀', () => {
    const registration = demoDefinition().setup({})

    expect(registration.routes?.map((route) => route.path)).toEqual(['/demo', '/demo/toolbox'])
    expect(registration.routes?.[0]?.meta).toMatchObject({ title: '演示模块', group: '演示模块', devOnly: true })
    expect(registration.components).toEqual({ 'demo:toolbox': {} })
    expect(registration.fieldRenderers).toEqual([{ key: 'demo:amount', component: {}, fieldType: 'amount' }])
    expect(registration.icons).toEqual({ 'demo:sparkles': 'sparkles' })
    expect(registration.cards).toEqual([{ key: 'demo:summary', title: '模块概览' }])
    expect(registration.regions).toEqual([{ key: 'demo:hero', area: 'layout.header', component: {}, order: 10 }])
    expect(registration.themeTokens).toEqual([
      { key: 'demo:brand', tokens: { '--bms-color-primary': '#3a7bd5' }, mode: 'brand' },
    ])
    expect(registration.i18nPacks).toEqual([
      { key: 'demo:zh-cn', messages: { 'demo.title': '演示模块' } },
      { key: 'demo:en', messages: { 'demo.title': 'Demo module' } },
    ])
  })

  it('路由组件为异步加载器（可解析）', async () => {
    const registration = demoDefinition().setup({})
    for (const route of registration.routes ?? []) {
      await expect(route.component()).resolves.toEqual({})
    }
  })
})
