/** 异常与空状态用例（03_02）。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { EmptyState, ErrorPage, LoadingMask, SkeletonBlock, useFeedback } from '../src'

const stubs = {
  ElButton: { template: '<button><slot /></button>' },
  ElSkeleton: { props: ['rows'], template: '<div class="el-skeleton"><slot name="template" /><slot /></div>' },
  ElSkeletonItem: { template: '<div class="el-skeleton-item" />' },
}

describe('ErrorPage', () => {
  it('按状态码给缺省文案与重试可见性', () => {
    const forbidden = mount(ErrorPage, { props: { code: 403 }, global: { stubs } })
    expect(forbidden.find('[data-test="error-code"]').text()).toBe('403')
    expect(forbidden.text()).toContain('无访问权限')
    expect(forbidden.find('[data-test="error-retry"]').exists()).toBe(false)

    const notFound = mount(ErrorPage, { props: { code: 404 }, global: { stubs } })
    expect(notFound.text()).toContain('页面不存在')

    const serverError = mount(ErrorPage, { props: { code: 500 }, global: { stubs } })
    expect(serverError.text()).toContain('服务异常')
    expect(serverError.find('[data-test="error-retry"]').exists()).toBe(true)
  })

  it('自定义文案与事件', async () => {
    const wrapper = mount(ErrorPage, {
      props: { code: 500, title: '维护中', description: '稍后开放' },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('维护中')
    await wrapper.find('[data-test="error-retry"]').trigger('click')
    await wrapper.find('[data-test="error-home"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.emitted('home')).toHaveLength(1)
  })
})

describe('EmptyState', () => {
  it('按场景映射标题并渲染动作插槽', () => {
    const wrapper = mount(EmptyState, {
      props: { type: 'permission' },
      slots: { action: '<button data-test="action">申请</button>' },
    })
    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('暂无访问权限')
    expect(wrapper.attributes('data-type')).toBe('permission')
    expect(wrapper.find('[data-test="action"]').exists()).toBe(true)
  })

  it('未知场景回退到 data', () => {
    const wrapper = mount(EmptyState, { props: { type: 'data', title: '空空如也' } })
    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('空空如也')
  })
})

describe('SkeletonBlock', () => {
  it('卡片形态渲染骨架项', () => {
    const wrapper = mount(SkeletonBlock, { props: { variant: 'card' }, global: { stubs } })
    expect(wrapper.findAll('.el-skeleton-item').length).toBeGreaterThan(0)
    expect(wrapper.attributes('data-variant')).toBe('card')
  })
})

describe('LoadingMask', () => {
  it('延迟展示防闪烁', async () => {
    const wrapper = mount(LoadingMask, { props: { loading: true, delay: 40 }, slots: { default: '<div>x</div>' } })
    expect(wrapper.find('[data-test="loading-mask"]').exists()).toBe(false)

    await new Promise((resolve) => setTimeout(resolve, 80))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="loading-mask"]').exists()).toBe(true)

    await wrapper.setProps({ loading: false })
    expect(wrapper.find('[data-test="loading-mask"]').exists()).toBe(false)
  })

  it('delay 为 0 立即展示', () => {
    const wrapper = mount(LoadingMask, { props: { loading: true, delay: 0 }, slots: { default: '<div>x</div>' } })
    expect(wrapper.find('[data-test="loading-mask"]').exists()).toBe(true)
  })
})

describe('useFeedback', () => {
  it('四态切换', () => {
    const feedback = useFeedback()
    expect(feedback.state.value).toBe('loading')
    feedback.ready()
    expect(feedback.state.value).toBe('ready')
    feedback.empty()
    expect(feedback.state.value).toBe('empty')
    feedback.error()
    expect(feedback.state.value).toBe('error')
    feedback.begin()
    expect(feedback.state.value).toBe('loading')
  })

  it('仅错误态且注入回调时重试', () => {
    const feedback = useFeedback()
    const retry = vi.fn()
    expect(feedback.retry()).toBe(false)

    feedback.setRetry(retry)
    expect(feedback.retry()).toBe(false)

    feedback.error()
    expect(feedback.retry()).toBe(true)
    expect(retry).toHaveBeenCalledTimes(1)
  })
})
