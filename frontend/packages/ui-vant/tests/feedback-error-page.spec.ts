/** 错误页用例（Kiwi 751）：三码文案 / 操作 / 事件 / 自定义覆盖。 */

import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import { ErrorPage } from '../src'

import { mountWithPlugins } from './helpers/mount'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: { template: '<div />' } }],
})

function mountPage(options: Parameters<typeof mount>[1] = {}) {
  return mountWithPlugins(ErrorPage, {
    ...options,
    global: { ...(options.global ?? {}), plugins: [router] },
  })
}

describe('错误页（Kiwi 751）', () => {
  it('404：缺省标题 / 插画 / 单个「返回首页」动作；点击 emit home 并跳转', async () => {
    const wrapper = mountPage()
    expect(wrapper.find('.bms-error-page-title').text()).toBe('页面不存在（或已被移除）')
    expect(wrapper.find('.bms-error-page-illustration').attributes('src')).toContain('data:image/svg+xml')
    const buttons = wrapper.findAll('.bms-error-page-actions button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]?.text()).toContain('返回首页')

    await buttons[0]?.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('home')).toHaveLength(1)
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('403：两个动作且「联系管理员」仅 emit', async () => {
    const wrapper = mountPage({ props: { code: 403 } })
    const buttons = wrapper.findAll('.bms-error-page-actions button')
    expect(buttons).toHaveLength(2)
    expect(wrapper.find('.bms-error-page-illustration').attributes('src')).toContain('data:image/svg+xml')
    await wrapper.find('[data-action="contact"]').trigger('click')
    expect(wrapper.emitted('contact')).toHaveLength(1)
  })

  it('500：刷新重试 + 返回首页；自定义 actions 完全覆盖并执行 handler', async () => {
    const wrapper = mountPage({ props: { code: 500 } })
    const labels = wrapper.findAll('.bms-error-page-actions button').map((button) => button.text())
    expect(labels[0]).toContain('刷新重试')
    expect(labels[1]).toContain('返回首页')
    expect(wrapper.find('.bms-error-page-illustration').attributes('src')).toContain('data:image/svg+xml')
    // `retry` 缺省行为触发 window.location.reload（jsdom 不可测真实刷新）：此处只断言动作接线与 emit 面
    expect(wrapper.find('[data-action="retry"]').exists()).toBe(true)
    await wrapper.find('[data-action="home"]').trigger('click')
    expect(wrapper.emitted('home')).toHaveLength(1)

    const handler = vi.fn()
    const custom = mountPage({
      props: { actions: [{ key: 'custom', text: '自定义', handler }] },
    })
    expect(custom.findAll('.bms-error-page-actions button')).toHaveLength(1)
    await custom.find('.bms-error-page-actions button').trigger('click')
    expect(handler).toHaveBeenCalledTimes(1)
    expect(custom.emitted('home')).toBeUndefined()
  })

  it('自定义 title / description；不展示技术堆栈', () => {
    const wrapper = mountPage({ props: { title: '出错了', description: '请稍后重试' } })
    expect(wrapper.find('.bms-error-page-title').text()).toBe('出错了')
    expect(wrapper.find('.bms-error-page-description').text()).toBe('请稍后重试')
    expect(wrapper.text()).not.toContain('at ')
  })
})
