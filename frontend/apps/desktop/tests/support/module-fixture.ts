/**
 * 宿主模块用例共用夹具：远端演示模块的清单条目与模块定义（与 `frontend/modules/demo` 声明同形）。
 *
 * 远端形态下模块产物由独立工程构建、不可从宿主用例直接 import，故以同形夹具经
 * `@module-federation/runtime` 替身注入（见各 spec 的 `vi.mock`）。
 */

import { MODULE_CONTRACT_VERSION, type ModuleDefinition, type ModuleManifestEntry } from '@bms/core'

/** 远端演示模块清单条目（绝对入口 URL + `mode: remote`）。 */
export const REMOTE_ENTRY: ModuleManifestEntry = {
  name: 'demo',
  entry: 'http://localhost:5002/demo/0.1.0/remoteEntry.js',
  version: '0.1.0',
  mode: 'remote',
  enabled: true,
}

/** 未迁移模块清单条目（本地形态：入口为模块源码标识，宿主本地入口表当前为空）。 */
export const LOCAL_ENTRY: ModuleManifestEntry = {
  name: 'legacy',
  entry: 'legacy',
  version: '1.0.0',
  mode: 'local',
  enabled: true,
}

/** 远端演示模块定义（每次调用返回新实例，避免用例间共享注册声明）。 */
export function demoDefinition(): ModuleDefinition {
  return {
    manifest: { name: 'demo', version: '0.1.0', contractVersion: MODULE_CONTRACT_VERSION },
    setup: () => ({
      routes: [
        {
          path: '/demo',
          name: 'DemoHome',
          component: async () => ({}),
          meta: { title: '演示模块', keepAlive: true, group: '演示模块', groupIcon: 'sparkles', devOnly: true },
        },
        {
          path: '/demo/toolbox',
          name: 'DemoToolbox',
          component: async () => ({}),
          meta: { title: '组件契约演示', group: '演示模块', devOnly: true },
        },
      ],
      components: { 'demo:toolbox': {} },
      fieldRenderers: [{ key: 'demo:amount', component: {}, fieldType: 'amount' }],
      icons: { 'demo:sparkles': 'sparkles' },
      cards: [{ key: 'demo:summary', title: '模块概览' }],
      regions: [{ key: 'demo:hero', area: 'layout.header', component: {}, order: 10 }],
      themeTokens: [{ key: 'demo:brand', tokens: { '--bms-color-primary': '#3a7bd5' }, mode: 'brand' }],
      i18nPacks: [
        { key: 'demo:zh-cn', messages: { 'demo.title': '演示模块' } },
        { key: 'demo:en', messages: { 'demo.title': 'Demo module' } },
      ],
    }),
  }
}
