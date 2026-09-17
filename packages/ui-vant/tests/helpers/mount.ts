/** 组件测试基座：预挂 i18n（容器件文案最小集），与移动端宿主文案一致。 */

import { mount } from '@vue/test-utils'
import type { MountingOptions, VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { Component } from 'vue'

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

export function mountWithPlugins(
  component: Component,
  options: MountingOptions<Record<string, unknown>> = {},
): VueWrapper {
  const globalOptions = options.global ?? {}
  const plugins = [...(globalOptions.plugins ?? []), i18n]
  return mount(component, { ...options, global: { ...globalOptions, plugins } }) as VueWrapper
}
