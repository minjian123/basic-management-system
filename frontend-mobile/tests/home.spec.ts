/** 默认页冒烟（Kiwi 20）：标题与 backend 连通状态渲染（mock 接口，含降级）。 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAppInfo } from '@/api/http'
import { i18n } from '@/i18n'
import HomeView from '@/views/HomeView.vue'

vi.mock('@/api/http', () => ({ fetchAppInfo: vi.fn() }))

describe('HomeView 默认页（Kiwi 20）', () => {
  beforeEach(() => {
    vi.mocked(fetchAppInfo).mockResolvedValue({ name: 'BMS 基础管理系统', version: '0.1.0' })
  })

  it('渲染标题并展示 backend 连通状态', async () => {
    const wrapper = mount(HomeView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('BMS 基础管理系统')
    expect(wrapper.text()).toContain('BMS 基础管理系统 0.1.0')
  })

  it('backend 未连通时展示降级文案', async () => {
    vi.mocked(fetchAppInfo).mockRejectedValue(new Error('offline'))
    const wrapper = mount(HomeView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain('后端服务未连通')
  })
})
