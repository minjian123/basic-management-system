/**
 * 演示模块定义（Module Federation remote 入口：**默认导出**模块定义）。
 *
 * 独立工程、独立构建、独立产物（`dist/remoteEntry.js` + 页面异步分包）；宿主按模块清单
 * 运行期加载本容器暴露的 `./module`（模块定义），经统一装配器倒入八类扩展点注册表。
 * 仅开发态进菜单（不进入生产菜单）。
 */

import { WorkbenchCardProvider, defineModule } from '@bms/core'

/** 演示模块（清单 `name` / `version` 须与宿主 `public/modules.json` 条目严格一致）。 */
export const demoModule = defineModule({
  manifest: { name: 'demo', version: '0.1.0' },
  setup: () => ({
    routes: [
      {
        path: '/demo',
        name: 'DemoHome',
        component: () => import('./views/DemoHome.vue'),
        meta: { title: '演示模块', keepAlive: true },
      },
      {
        path: '/demo/toolbox',
        name: 'DemoToolbox',
        component: () => import('./views/DemoToolbox.vue'),
        meta: { title: '组件契约演示' },
      },
    ],
    components: { 'demo:toolbox': () => import('./views/DemoToolbox.vue') },
    fieldRenderers: [{ key: 'demo:amount', component: () => import('./views/DemoHome.vue'), fieldType: 'amount' }],
    icons: { 'demo:sparkles': 'sparkles' },
    cards: [new WorkbenchCardProvider('demo:summary', () => import('./views/DemoHome.vue'), '模块概览')],
    regions: [
      { key: 'demo:hero', area: 'layout.header', component: () => import('./views/DemoToolbox.vue'), order: 10 },
    ],
    themeTokens: [{ key: 'demo:brand', tokens: { '--bms-color-primary': '#3a7bd5' }, mode: 'brand' }],
    i18nPacks: [
      {
        key: 'demo:zh-cn',
        messages: { 'demo.title': '演示模块', 'demo.toolbox': '组件契约演示', 'demo.summary': '模块概览' },
      },
      {
        key: 'demo:en',
        messages: {
          'demo.title': 'Demo module',
          'demo.toolbox': 'Component contract demo',
          'demo.summary': 'Module overview',
        },
      },
    ],
  }),
})

export default demoModule
