// kiwi_id: 981
/** 模块契约用例工厂用例（同一契约多实现：以最小模块实现跑通套件，模块侧同套件见 `modules/demo/tests/module-contract.spec.ts`）。 */

import { describeModuleContract } from '@bms/core/testing'

import { MODULE_CONTRACT_VERSION, defineModule } from '../src'

const minimal = defineModule({
  manifest: { name: 'sample', version: '1.0.0', contractVersion: MODULE_CONTRACT_VERSION },
  setup: () => ({
    routes: [{ path: '/sample', name: 'SampleHome', component: async () => ({}) }],
    components: { 'sample:panel': {} },
    regions: [{ key: 'sample:hero', area: 'layout.header', component: {} }],
    themeTokens: [{ key: 'sample:brand', tokens: { '--bms-color-primary': '#3a7bd5' } }],
    i18nPacks: [{ key: 'sample:zh-cn', messages: { 'sample.title': '样例' } }],
  }),
})

describeModuleContract('模块契约工厂（Kiwi 981 · 最小实现）', {
  definition: minimal,
  manifestEntry: { name: 'sample', entry: 'sample', version: '1.0.0', mode: 'local', enabled: true },
  facts: { packageVersion: '1.0.0', sharedViolations: [], isolationViolations: [] },
})
