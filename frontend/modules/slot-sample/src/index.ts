/* eslint-disable @typescript-eslint/triple-slash-reference -- Module Federation 类型声明生成以 plain tsc 编译，需引用 env.d.ts 载入环境声明（版本常量与 .vue shim） */
/// <reference path="./env.d.ts" />
/**
 * 具名插槽样例插件定义（Module Federation remote 入口：**默认导出**模块定义）。
 *
 * 与「首个模块样例」`sample` 的差异：本模块**不声明路由**（无页面、不进菜单），只向宿主页具名插槽
 * `sys.user.detail.tabs` 注册区域项；数据与写操作归**后端契约**（platform 服务
 * `/api/v1/user-extensions`，权限码 `sys:user-extension:query` / `sys:user-extension:update`），
 * 模块只渲染并**经宿主注入的 `api` 能力**调用。
 *
 * 独立工程、独立构建、独立产物（`dist/remoteEntry.js` + 区域件异步分包 + `module.meta.json`）。
 */

import { MODULE_CONTRACT_VERSION, defineModule } from '@bms/core'

import { SLOT_SAMPLE_MESSAGES_EN, SLOT_SAMPLE_MESSAGES_ZH_CN } from './i18n/messages'
import { applyHostContext } from './runtime'

/** 具名插槽标识（`{域}.{页面}.{区域}`；宿主页「用户详情」声明本挂接点）。 */
export const USER_DETAIL_TABS_SLOT = 'sys.user.detail.tabs'

/** 后端写权限码（与后端契约端点同源；区域项 `perm` 引用同一权限码）。 */
export const USER_EXTENSION_UPDATE_PERMISSION = 'sys:user-extension:update'

/** 具名插槽样例插件（清单 `name` / `version` 须与宿主 `public/modules.json` 条目严格一致；版本构建期注入）。 */
export const slotSampleModule = defineModule({
  manifest: { name: 'slot-sample', version: __BMS_MODULE_VERSION__, contractVersion: MODULE_CONTRACT_VERSION },
  setup: (context) => {
    // 只经注入上下文访问宿主能力（只读快照）：记录只读 router（读取宿主页实体标识）与请求能力 api。
    applyHostContext(context)
    return {
      regions: [
        {
          key: 'slot-sample:user-extension',
          area: USER_DETAIL_TABS_SLOT,
          component: () => import('./components/SlotExtensionTab.vue'),
          order: 20,
          title: '用户扩展示例',
        },
        {
          key: 'slot-sample:user-extension-detail',
          area: USER_DETAIL_TABS_SLOT,
          component: () => import('./components/SlotExtensionDetailTab.vue'),
          order: 30,
          title: '扩展示例明细',
          // 按权限显隐：无写权限即不渲染该项（宿主页其余正常）；前端显隐非鉴权，后端强制校验。
          perm: USER_EXTENSION_UPDATE_PERMISSION,
          permMode: 'any',
        },
      ],
      i18nPacks: [
        { key: 'slot-sample:zh-cn', messages: SLOT_SAMPLE_MESSAGES_ZH_CN },
        { key: 'slot-sample:en', messages: SLOT_SAMPLE_MESSAGES_EN },
      ],
    }
  },
})

export default slotSampleModule
