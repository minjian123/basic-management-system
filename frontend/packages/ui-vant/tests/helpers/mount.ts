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
      feedback: {
        loading: '加载中…',
        error403Title: '没有访问权限（如需申请请联系管理员）',
        error404Title: '页面不存在（或已被移除）',
        error500Title: '服务开小差了（请稍后重试）',
        backHome: '返回首页',
        retry: '刷新重试',
        contactAdmin: '联系管理员',
        emptyList: '暂无数据',
        emptySearch: '未找到相关内容',
        emptyTodo: '暂无待办，享受这一刻',
        emptyMessage: '暂无消息',
        goCreate: '去创建',
        clearFilters: '清除筛选',
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
