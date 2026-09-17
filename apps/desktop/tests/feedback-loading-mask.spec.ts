/** 内容遮罩用例（Kiwi 729）：delay 防闪 / fullscreen / 文案。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LoadingMask from '@/components/feedback/LoadingMask.vue'

import { mountWithPlugins } from './helpers/mount'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

function mountMask(props: Record<string, unknown> = {}) {
  return mountWithPlugins(LoadingMask, { props })
}

describe('内容遮罩（Kiwi 729）', () => {
  it('delay 防闪：延时内不显示、超时显示；loading=false 立即隐藏', async () => {
    const wrapper = mountMask({ loading: false, delay: 200 })
    await wrapper.setProps({ loading: true })
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(false)

    vi.advanceTimersByTime(200)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(true)

    await wrapper.setProps({ loading: false })
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(false)
  })

  it('delay=0 立即显示', async () => {
    const wrapper = mountMask({ loading: false, delay: 0 })
    await wrapper.setProps({ loading: true })
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(true)
  })

  it('文案缺省与自定义；fullscreen 类', () => {
    const preset = mountMask({ loading: true, delay: 0 })
    expect(preset.text()).toContain('加载中…')

    const customText = mountMask({ loading: true, delay: 0, text: '正在保存…' })
    expect(customText.text()).toContain('正在保存…')

    const fullscreen = mountMask({ fullscreen: true })
    expect(fullscreen.find('.bms-loading-mask--fullscreen').exists()).toBe(true)
  })

  it('包裹内容始终渲染', () => {
    const wrapper = mountWithPlugins(LoadingMask, {
      props: { loading: true, delay: 0 },
      slots: { default: '<p class="content">正文</p>' },
    })
    expect(wrapper.find('.content').exists()).toBe(true)
    expect(wrapper.find('.bms-loading-mask-overlay').exists()).toBe(true)
  })
})
