/** 组件测试基座：预挂 pinia / i18n，可选 router 等通过 options.global 覆盖。 */

import { mount } from '@vue/test-utils'
import type { MountingOptions, VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import type { Component } from 'vue'

import { i18n } from '@/i18n'

export function mountWithPlugins(
  component: Component,
  options: MountingOptions<Record<string, unknown>> = {},
): VueWrapper {
  const globalOptions = options.global ?? {}
  const plugins = [...(globalOptions.plugins ?? []), createPinia(), i18n]
  return mount(component, { ...options, global: { ...globalOptions, plugins } }) as VueWrapper
}
