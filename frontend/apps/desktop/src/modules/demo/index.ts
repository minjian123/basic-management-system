/** 演示模块定义（本地模块；阶段五远端模块按同一契约接入）。 */

import { defineModule } from '@bms/core'

/** 演示模块。 */
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
    icons: { demo: 'sparkles' },
  }),
})
