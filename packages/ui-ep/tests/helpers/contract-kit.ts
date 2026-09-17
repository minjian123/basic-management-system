/** 契约套件挂载适配：`@vue/test-utils` ↔ `@bms/core/testing` 结构接口（i18n 文案最小集）。 */

import { mount } from '@vue/test-utils'
import { createContractKit, type MountLike } from '@bms/vue/testing'
import { createI18n } from 'vue-i18n'

import * as plugin from '../../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      container: {
        fullscreenTip: '已进入全屏，按 Esc 退出',
        retry: '重试',
        loadingFailed: '加载失败',
        emptyText: '暂无数据',
      },
    },
  },
})

export const contractKit = createContractKit({
  mount: mount as unknown as MountLike,
  components: plugin as unknown as Record<string, unknown>,
  configurePermissionChecker: plugin.configurePermissionChecker,
  global: { plugins: [i18n] },
})
