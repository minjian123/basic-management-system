/** 四态容器件用例（04_01_03）。 */

import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StatusContainer } from '../src'

const stubs = { ElButton: { template: '<button><slot /></button>' } }

afterEach(() => vi.useRealTimers())

describe('StatusContainer', () => {
  it('就绪态渲染内容，四态切换正确', async () => {
    const wrapper = mount(StatusContainer, {
      props: { status: 'ready', delay: 0 },
      slots: { default: '<div data-test="content">内容</div>' },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
    expect(wrapper.attributes('data-status')).toBe('ready')

    await wrapper.setProps({ status: 'empty' })
    expect(wrapper.find('[data-test="status-empty"]').exists()).toBe(true)

    await wrapper.setProps({ status: 'error' })
    expect(wrapper.find('[data-test="status-error"]').exists()).toBe(true)

    await wrapper.setProps({ status: 'loading' })
    expect(wrapper.find('[data-test="status-loading"]').exists()).toBe(true)
    expect(wrapper.emitted('status-change')?.map((args) => args[0])).toEqual(['ready', 'empty', 'error', 'loading'])
  })

  it('延迟内转就绪不显示加载态（防闪）', async () => {
    vi.useFakeTimers()
    const wrapper = mount(StatusContainer, {
      props: { status: 'loading', delay: 200 },
      slots: { default: '<div data-test="content">内容</div>' },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="status-loading"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)

    await wrapper.setProps({ status: 'ready' })
    vi.advanceTimersByTime(300)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="status-loading"]').exists()).toBe(false)
  })

  it('超过延迟后显示加载态', async () => {
    vi.useFakeTimers()
    const wrapper = mount(StatusContainer, {
      props: { status: 'loading', delay: 100 },
      slots: { default: '<div>x</div>' },
      global: { stubs },
    })
    vi.advanceTimersByTime(120)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="status-loading"]').exists()).toBe(true)
  })

  it('空 / 错误插槽可覆盖内置形态', () => {
    const wrapper = mount(StatusContainer, {
      props: { status: 'empty', delay: 0 },
      slots: { empty: '<div data-test="empty-slot">自定义空</div>', default: '<div>x</div>' },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="empty-slot"]').exists()).toBe(true)

    const custom = mount(StatusContainer, {
      props: { status: 'error', delay: 0, retryable: true },
      slots: { error: '<div data-test="error-slot">自定义错误</div>', default: '<div>x</div>' },
      global: { stubs },
    })
    expect(custom.find('[data-test="error-slot"]').exists()).toBe(true)
  })

  it('重试按钮按 retryable 开关并派发 retry', async () => {
    const wrapper = mount(StatusContainer, {
      props: { status: 'error', delay: 0, retryable: true },
      slots: { default: '<div>x</div>' },
      global: { stubs },
    })
    await wrapper.find('[data-test="status-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)

    const noRetry = mount(StatusContainer, {
      props: { status: 'error', delay: 0 },
      slots: { default: '<div>x</div>' },
      global: { stubs },
    })
    expect(noRetry.find('[data-test="status-retry"]').exists()).toBe(false)
  })

  it('keepContent 时非就绪态内容隐藏但保留挂载', async () => {
    const wrapper = mount(StatusContainer, {
      props: { status: 'loading', delay: 0, keepContent: true },
      slots: { default: '<div data-test="content">内容</div>' },
      global: { stubs },
    })
    const content = wrapper.find('[data-test="content"]')
    expect(content.exists()).toBe(true)
    expect(wrapper.find('.bms-status-container__content').attributes('style')).toContain('display: none')
  })

  it('内置空 / 错误文案可配', () => {
    const empty = mount(StatusContainer, {
      props: { status: 'empty', delay: 0, emptyText: '没有记录' },
      slots: { default: '<div>x</div>' },
      global: { stubs },
    })
    expect(empty.text()).toContain('没有记录')

    const error = mount(StatusContainer, {
      props: { status: 'error', delay: 0, errorText: '出错了' },
      slots: { default: '<div>x</div>' },
      global: { stubs },
    })
    expect(error.text()).toContain('出错了')
  })
})
