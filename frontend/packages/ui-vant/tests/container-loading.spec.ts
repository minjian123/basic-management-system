/** 加载遮罩容器用例（Kiwi 749）：四态互斥 / 延迟显示 / 重试。 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { LoadingContainer } from '../src'

import { mountWithPlugins } from './helpers/mount'

type Wrapper = ReturnType<typeof mountWithPlugins>

function vmOf(wrapper: Wrapper): { state: string } {
  return wrapper.vm as unknown as { state: string }
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('加载遮罩容器（Kiwi 749）', () => {
  it('四态互斥优先级：loading > error > empty > content', async () => {
    const wrapper = mountWithPlugins(LoadingContainer, {
      props: { delay: 0 },
      slots: { default: '<div class="content">内容</div>' },
    })
    expect(wrapper.find('.content').exists()).toBe(true)
    expect(vmOf(wrapper).state).toBe('content')

    await wrapper.setProps({ empty: true })
    expect(wrapper.find('[data-testid="empty-state"]').exists()).toBe(true)

    await wrapper.setProps({ error: '出错了' })
    expect(wrapper.find('[data-testid="error-state"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('出错了')

    await wrapper.setProps({ loading: true })
    expect(wrapper.find('[data-testid="loading-state"]').exists()).toBe(true)

    await wrapper.setProps({ loading: false, error: false, empty: false })
    expect(wrapper.find('.content').exists()).toBe(true)
  })

  it('delay 防闪烁：快请求不显示、慢请求显示、显示后即时隐藏', async () => {
    vi.useFakeTimers()
    const wrapper = mountWithPlugins(LoadingContainer, {
      props: { delay: 200 },
      slots: { default: '<div class="content">内容</div>' },
    })

    // 快请求（< delay）：从未显示加载态
    await wrapper.setProps({ loading: true })
    vi.advanceTimersByTime(100)
    await nextTick()
    expect(wrapper.find('[data-testid="loading-state"]').exists()).toBe(false)
    await wrapper.setProps({ loading: false })
    vi.advanceTimersByTime(500)
    await nextTick()
    expect(wrapper.find('[data-testid="loading-state"]').exists()).toBe(false)
    expect(wrapper.find('.content').exists()).toBe(true)

    // 慢请求：delay 后显示；随后 loading=false 即时隐藏
    await wrapper.setProps({ loading: true })
    vi.advanceTimersByTime(200)
    await nextTick()
    expect(wrapper.find('[data-testid="loading-state"]').exists()).toBe(true)
    await wrapper.setProps({ loading: false })
    await nextTick()
    expect(wrapper.find('[data-testid="loading-state"]').exists()).toBe(false)
  })

  it('mode 三形态与 #loading 插槽优先；role 标记', async () => {
    const skeleton = mountWithPlugins(LoadingContainer, {
      props: { loading: true, delay: 0, mode: 'skeleton' },
    })
    expect(skeleton.find('.bms-loading-container-skeleton').exists()).toBe(true)
    expect(skeleton.find('[data-testid="loading-state"]').attributes('role')).toBe('status')

    const spin = mountWithPlugins(LoadingContainer, {
      props: { loading: true, delay: 0, mode: 'spin' },
    })
    expect(spin.find('.bms-loading-container-spin').exists()).toBe(true)

    const mask = mountWithPlugins(LoadingContainer, {
      props: { loading: true, delay: 0, mode: 'mask' },
    })
    expect(mask.find('.bms-loading-container-mask').exists()).toBe(true)

    const custom = mountWithPlugins(LoadingContainer, {
      props: { loading: true, delay: 0 },
      slots: { loading: '<div class="my-loading">载入中</div>' },
    })
    expect(custom.find('.my-loading').exists()).toBe(true)
    expect(custom.find('.bms-loading-container-mask').exists()).toBe(false)
  })

  it('empty / error 插槽优先；缺省错误文本与重试自锁', async () => {
    const wrapper = mountWithPlugins(LoadingContainer, {
      props: { error: true as unknown as string, delay: 0 },
    })
    expect(wrapper.find('[data-testid="error-state"]').text()).toContain('加载失败')
    expect(wrapper.find('[data-testid="error-state"]').attributes('role')).toBe('alert')

    const button = wrapper.find('[data-testid="retry-button"]')
    expect(button.text()).toContain('重试')
    await button.trigger('click')
    expect((wrapper.emitted('retry') as unknown[][]).length).toBe(1)
    expect((wrapper.find('[data-testid="retry-button"]').element as HTMLButtonElement).disabled).toBe(true)

    await wrapper.find('[data-testid="retry-button"]').trigger('click')
    expect((wrapper.emitted('retry') as unknown[][]).length).toBe(1)

    // loading 变化复位自锁
    await wrapper.setProps({ loading: true })
    await wrapper.setProps({ loading: false })
    await nextTick()
    expect((wrapper.find('[data-testid="retry-button"]').element as HTMLButtonElement).disabled).toBe(false)

    const custom = mountWithPlugins(LoadingContainer, {
      props: { empty: true, delay: 0 },
      slots: { empty: '<div class="my-empty">空空如也</div>' },
    })
    expect(custom.find('.my-empty').exists()).toBe(true)

    const fallback = mountWithPlugins(LoadingContainer, { props: { empty: true, delay: 0 } })
    expect(fallback.find('[data-testid="empty-state"]').text()).toContain('暂无数据')

    const customError = mountWithPlugins(LoadingContainer, {
      props: { error: 'x', delay: 0 },
      slots: { error: '<div class="my-error">自定义错误</div>' },
    })
    expect(customError.find('.my-error').exists()).toBe(true)
  })

  it('minHeight 注入', () => {
    const wrapper = mountWithPlugins(LoadingContainer, {
      props: { loading: true, delay: 0, minHeight: 300 },
    })
    const status = wrapper.find('[data-testid="loading-state"]')
    expect(status.attributes('style')).toContain('min-height: 300px')
  })
})
