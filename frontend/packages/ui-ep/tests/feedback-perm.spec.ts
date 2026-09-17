/** 反馈（错误页 / 空态）与权限按钮用例：注入点语义与渲染。 */

import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { configurePermissionChecker, EmptyState, ErrorPage, PermButton } from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      feedback: {
        error404Title: '页面不存在（或已被移除）',
        error403Title: '没有访问权限（如需申请请联系管理员）',
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

afterEach(() => {
  configurePermissionChecker(undefined)
})

function mountWithI18n(component: Parameters<typeof mount>[0], options: Parameters<typeof mount>[1] = {}) {
  return mount(component, {
    ...options,
    global: { ...(options.global ?? {}), plugins: [i18n] },
  })
}

describe('EmptyState（迁移）', () => {
  it('缺省场景文案与插画；size=small 类', () => {
    const wrapper = mountWithI18n(EmptyState, { props: { type: 'list' } })
    expect(wrapper.find('.bms-empty-state').exists()).toBe(true)
    expect(wrapper.find('.bms-empty-state-title').text()).toBe('暂无数据')
    expect(wrapper.find('.bms-empty-state-illustration').exists()).toBe(true)
    expect(wrapper.find('.bms-empty-state-action').exists()).toBe(false)

    const small = mountWithI18n(EmptyState, { props: { type: 'search', size: 'small' } })
    expect(small.find('.bms-empty-state--small').exists()).toBe(true)
    expect(small.find('.bms-empty-state-title').text()).toBe('未找到相关内容')
  })

  it('引导按钮：权限未注入（空集）不渲染；注入放行后渲染并可点击', async () => {
    const blocked = mountWithI18n(EmptyState, {
      props: { type: 'list', action: { key: 'create' }, actionPerm: 'user:create' },
    })
    expect(blocked.find('.bms-empty-state-action').exists()).toBe(false)

    configurePermissionChecker((codes) => codes.includes('user:create'))
    const allowed = mountWithI18n(EmptyState, {
      props: { type: 'list', action: { key: 'create' }, actionPerm: 'user:create' },
    })
    expect(allowed.find('.bms-empty-state-action').exists()).toBe(true)
    expect(allowed.find('.bms-empty-state-action').text()).toContain('去创建')

    await allowed.find('.bms-empty-state-action button').trigger('click')
    expect(allowed.emitted('action')).toBeTruthy()
  })
})

describe('ErrorPage（迁移）', () => {
  it('404：缺省标题与单个「返回首页」动作', () => {
    const wrapper = mountWithI18n(ErrorPage)
    expect(wrapper.find('.bms-error-page-title').text()).toBe('页面不存在（或已被移除）')
    const buttons = wrapper.findAll('.bms-error-page-actions button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]?.text()).toContain('返回首页')
  })

  it('403：两个动作且「联系管理员」仅 emit', async () => {
    const wrapper = mountWithI18n(ErrorPage, { props: { code: 403 } })
    const buttons = wrapper.findAll('.bms-error-page-actions button')
    expect(buttons).toHaveLength(2)
    await buttons[1]?.trigger('click')
    expect(wrapper.emitted('contact')).toBeTruthy()
  })

  it('500：刷新重试 + 返回首页；自定义 actions 完全覆盖并执行 handler', async () => {
    const wrapper = mountWithI18n(ErrorPage, { props: { code: 500 } })
    const labels = wrapper.findAll('.bms-error-page-actions button').map((button) => button.text())
    expect(labels[0]).toContain('刷新重试')
    expect(labels[1]).toContain('返回首页')

    const handler = vi.fn()
    const custom = mountWithI18n(ErrorPage, {
      props: { actions: [{ key: 'custom', text: '自定义', handler }] },
    })
    await custom.find('.bms-error-page-actions button').trigger('click')
    expect(handler).toHaveBeenCalledTimes(1)
    expect(custom.emitted('home')).toBeUndefined()
  })
})

describe('PermButton（迁移）', () => {
  it('权限未注入（空集）：hide 不渲染 / disable 渲染禁用', () => {
    const hidden = mountWithI18n(PermButton, { props: { perm: 'user:create' } })
    expect(hidden.find('button').exists()).toBe(false)

    const disabled = mountWithI18n(PermButton, {
      props: { perm: 'user:create', fallback: 'disable' },
      slots: { default: '新增' },
    })
    const button = disabled.find('button')
    expect(button.exists()).toBe(true)
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    expect(button.attributes('title')).toBe('没有操作权限')
  })

  it('注入放行后渲染并可点击 emit；无权限码不限制', async () => {
    configurePermissionChecker((codes) => codes.includes('user:create'))
    const allowed = mountWithI18n(PermButton, {
      props: { perm: 'user:create' },
      slots: { default: '新增' },
    })
    expect(allowed.find('.bms-perm-button').exists()).toBe(true)
    await allowed.find('button').trigger('click')
    expect(allowed.emitted('click')).toBeTruthy()

    const unrestricted = mountWithI18n(PermButton, { slots: { default: '普通' } })
    expect(unrestricted.find('button').exists()).toBe(true)
  })
})
