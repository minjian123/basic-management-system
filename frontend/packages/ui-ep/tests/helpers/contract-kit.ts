/** 契约套件挂载适配：`@vue/test-utils` ↔ `@bms/core/testing` 结构接口（i18n 文案最小集）。 */

import { mount } from '@vue/test-utils'
import { createContractKit, type MountLike } from '@bms/vue/testing'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

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
      common: { confirm: '确定' },
      input: {
        required: '必填项',
        emptyText: '—',
        outOfRange: '数值超出允许范围',
        selectPlaceholder: '请选择',
        searchPlaceholder: '搜索',
        maxCount: '最多可选 {max} 项',
        minCount: '至少选择 {min} 项',
        selectAll: '全选',
        notSet: '未设置',
        switchOn: '是',
        switchOff: '否',
        password: { weak: '弱', medium: '中', strong: '强', show: '显示', hide: '隐藏' },
      },
    },
  },
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: { template: '<div />' } }],
})

export const contractKit = createContractKit({
  mount: mount as unknown as MountLike,
  components: plugin as unknown as Record<string, unknown>,
  configurePermissionChecker: plugin.configurePermissionChecker,
  configureConfirm: plugin.configureConfirm,
  global: { plugins: [i18n, router] },
})
