/**
 * 首个模块样例定义（Module Federation remote 入口：**默认导出**模块定义）。
 *
 * 独立工程、独立构建、独立产物（`dist/remoteEntry.js` + 页面异步分包 + `module.meta.json`）；
 * 宿主按模块清单运行期加载本容器暴露的 `./module`（模块定义），经统一装配器倒入八类扩展点注册表。
 * 数据走模块内占位服务（真实接口随后续窗口联调）。
 */

import { MODULE_CONTRACT_VERSION, WorkbenchCardProvider, defineModule } from '@bms/core'

import { SAMPLE_MESSAGES_EN, SAMPLE_MESSAGES_ZH_CN } from './i18n/messages'
import { applyHostContext } from './runtime'

/** 首个模块样例（清单 `name` / `version` 须与宿主 `public/modules.json` 条目严格一致；版本构建期注入）。 */
export const sampleModule = defineModule({
  manifest: { name: 'sample', version: __BMS_MODULE_VERSION__, contractVersion: MODULE_CONTRACT_VERSION },
  setup: (context) => {
    // 只经注入上下文访问宿主能力（只读快照）：据权限码派生只读 / 可编辑状态；缺失项自行降级。
    applyHostContext(context)
    return {
      routes: [
        {
          path: '/sample',
          name: 'SampleList',
          component: () => import('./views/SampleList.vue'),
          meta: { title: '示例数据管理', icon: 'document', group: '示例模块', groupIcon: 'document', keepAlive: true },
        },
        {
          path: '/sample/detail/:id',
          name: 'SampleDetail',
          component: () => import('./views/SampleDetail.vue'),
          meta: { title: '记录详情', menu: false },
        },
        {
          path: '/sample/form/:id?',
          name: 'SampleForm',
          component: () => import('./views/SampleForm.vue'),
          meta: { title: '记录表单', menu: false },
        },
      ],
      components: { 'sample:priority-tag': () => import('./components/SamplePriorityTag.vue') },
      fieldRenderers: [
        { key: 'sample:priority', component: () => import('./components/SamplePriorityTag.vue'), fieldType: 'priority' },
      ],
      icons: { 'sample:record': 'document' },
      cards: [new WorkbenchCardProvider('sample:summary', () => import('./components/SampleSummaryCard.vue'), '示例数据概览')],
      regions: [
        { key: 'sample:header-badge', area: 'layout.header', component: () => import('./components/SampleHeaderBadge.vue'), order: 20 },
      ],
      themeTokens: [{ key: 'sample:accent', tokens: { '--bms-sample-accent': '#0f766e' }, mode: 'sample' }],
      i18nPacks: [
        { key: 'sample:zh-cn', messages: SAMPLE_MESSAGES_ZH_CN },
        { key: 'sample:en', messages: SAMPLE_MESSAGES_EN },
      ],
    }
  },
})

export default sampleModule
