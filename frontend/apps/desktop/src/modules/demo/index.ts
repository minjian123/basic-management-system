/** 演示模块定义（本地模块；阶段五远端模块按同一契约接入）。 */

import { WorkbenchCardProvider, defineModule } from '@bms/core'

/** 演示模块（**默认导出**为模块入口约定：清单驱动加载器取入口默认导出）。 */
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
