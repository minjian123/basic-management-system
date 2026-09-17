/** 内容遮罩用例（Kiwi 754）：delay 防闪 / fullscreen / 文案。 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { LoadingMask } from '../src'

import { mountWithPlugins } from './helpers/mount'

afterEach(() => {
  vi.useRealTimers()
})

describe('内容遮罩（Kiwi 754）', () => {
  it('delay 防闪烁：快请求不显示、慢请求显示、关闭即时隐藏', async () => {
    vi.useFakeTimers()
    const wrapper = mountWithPlugins(LoadingMask, { props: { delay: 200 } })
    await wrapper.setProps({ loading: true })
    vi.advanceTimersByTime(100)
    await nextTick()
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(false)

    vi.advanceTimersByTime(150)
    await nextTick()
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(true)

    await wrapper.setProps({ loading: false })
    await nextTick()
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(false)
  })

  it('delay=0 立即显示：role / aria / van-loading 与缺省文案', () => {
    const wrapper = mountWithPlugins(LoadingMask, { props: { loading: true, delay: 0 } })
    const overlay = wrapper.find('.bms-loading-mask-overlay')
    expect(overlay.exists()).toBe(true)
    expect(overlay.attributes('role')).toBe('status')
    expect(overlay.attributes('aria-busy')).toBe('true')
    expect(wrapper.find('.van-loading').exists()).toBe(true)
    expect(wrapper.find('.bms-loading-mask-text').text()).toBe('加载中…')
  })

  it('自定义 text / fullscreen 修饰类 / 包裹内容插槽', () => {
    const wrapper = mountWithPlugins(LoadingMask, {
      props: { loading: true, delay: 0, text: '同步中', fullscreen: true },
      slots: { default: '<div class="wrapped">内容</div>' },
    })
    expect(wrapper.find('.bms-loading-mask--fullscreen').exists()).toBe(true)
    expect(wrapper.find('.bms-loading-mask-text').text()).toBe('同步中')
    expect(wrapper.find('.wrapped').exists()).toBe(true)
  })

  it('卸载清理计时器（不抛出）', () => {
    vi.useFakeTimers()
    const wrapper = mountWithPlugins(LoadingMask, { props: { loading: true, delay: 500 } })
    expect(() => {
      wrapper.unmount()
      vi.advanceTimersByTime(600)
    }).not.toThrow()
  })
})
