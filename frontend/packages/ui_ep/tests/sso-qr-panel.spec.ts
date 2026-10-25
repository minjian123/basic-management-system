// kiwi_id: 2233
/** 扫码登录面板用例（05_04）：四态渲染 / 可扫码源过滤与多源切换 / 事件上抛 / 复用二维码件。 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('qrcode', () => ({
  default: {
    toDataURL: vi.fn(async () => 'data:image/png;base64,MOCKQR'),
  },
}))

import { SsoQrLoginPanel } from '../src'
import type { SsoQrLoginSourceAdapter } from '@bms/core'
import QrCode from '../src/components/display/QrCode.vue'

/** 入口清单（含非可扫码项）。 */
const PROVIDERS = [
  { idp_key: 'wecom-1', type: 'wecom', sort: 2, name: '企业微信' },
  { idp_key: 'dingtalk-1', type: 'dingtalk', sort: 1, name: '钉钉' },
  { idp_key: 'oidc-1', type: 'oidc', sort: 0, name: 'OIDC' },
]

/** 状态源桩。 */
type SourceStub = SsoQrLoginSourceAdapter & {
  init: ReturnType<typeof vi.fn>
  poll: ReturnType<typeof vi.fn>
}

function makeSource(overrides: Record<string, unknown> = {}): SourceStub {
  return {
    init: vi.fn().mockResolvedValue({ authorize_url: 'https://idp/authorize', state: 's1', expires_in: 600 }),
    poll: vi.fn().mockResolvedValue({ status: 'pending' }),
    ...overrides,
  } as unknown as SourceStub
}

afterEach(() => {
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('SsoQrLoginPanel 渲染与过滤', () => {
  it('渲染待扫与二维码，过滤可扫码源并保留名称', async () => {
    const wrapper = mount(SsoQrLoginPanel, { props: { providers: PROVIDERS, source: makeSource() } })
    await flushPromises()
    expect(wrapper.find('[data-test="sso-qr-panel"]').attributes('data-phase')).toBe('pending')
    const qr = wrapper.findComponent(QrCode)
    expect(qr.exists()).toBe(true)
    expect(qr.props('status')).toBe('active')
    expect(wrapper.find('[data-test="sso-qr-tip"]').text()).not.toBe('')
    expect(wrapper.findAll('[data-test^="sso-qr-switch-"]')).toHaveLength(2)
    expect(wrapper.find('[data-test="sso-qr-switch-wecom-1"]').text()).toBe('企业微信')
    wrapper.unmount()
  })

  it('无可扫码入口渲染空态 + 返回', async () => {
    const wrapper = mount(SsoQrLoginPanel, {
      props: { providers: [{ idp_key: 'oidc-1', type: 'oidc' }], source: makeSource() },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="sso-qr-empty"]').exists()).toBe(true)
    await wrapper.find('[data-test="sso-qr-back"]').trigger('click')
    expect(wrapper.emitted('back')).toBeTruthy()
    wrapper.unmount()
  })

  it('多源切换上抛 switch 并重取', async () => {
    const source = makeSource()
    const wrapper = mount(SsoQrLoginPanel, { props: { providers: PROVIDERS, source } })
    await flushPromises()
    const callsBefore = source.init.mock.calls.length
    await wrapper.find('[data-test="sso-qr-switch-wecom-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('switch')?.[0]).toEqual(['wecom-1'])
    expect(source.init.mock.calls.length).toBeGreaterThan(callsBefore)
    wrapper.unmount()
  })
})

describe('SsoQrLoginPanel 四态与事件', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('确认态上抛 confirmed（含 redirect）', async () => {
    const poll = vi.fn().mockResolvedValue({ status: 'confirmed', redirect: '/home' })
    const wrapper = mount(SsoQrLoginPanel, { props: { providers: PROVIDERS, source: makeSource({ poll }) } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.findComponent(QrCode).props('status')).toBe('confirmed')
    expect(wrapper.emitted('confirmed')?.[0]?.[0]).toEqual({ redirect: '/home' })
    wrapper.unmount()
  })

  it('过期态上抛 expired', async () => {
    const poll = vi.fn().mockResolvedValue({ status: 'expired' })
    const wrapper = mount(SsoQrLoginPanel, { props: { providers: PROVIDERS, source: makeSource({ poll }) } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.emitted('expired')).toBeTruthy()
    wrapper.unmount()
  })

  it('取址失败进入失败态并上抛 failed', async () => {
    const wrapper = mount(SsoQrLoginPanel, {
      props: { providers: PROVIDERS, source: makeSource({ init: vi.fn().mockRejectedValue(new Error('x')) }) },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="sso-qr-panel"]').attributes('data-phase')).toBe('failed')
    expect(wrapper.find('[data-test="sso-qr-error"]').exists()).toBe(true)
    expect(wrapper.emitted('failed')).toBeTruthy()
    wrapper.unmount()
  })

  it('终态下刷新按钮上抛 refresh', async () => {
    const poll = vi.fn().mockResolvedValue({ status: 'confirmed' })
    const wrapper = mount(SsoQrLoginPanel, { props: { providers: PROVIDERS, source: makeSource({ poll }) } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    await wrapper.find('[data-test="sso-qr-refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toBeTruthy()
    wrapper.unmount()
  })

  it('页面隐藏暂停轮询（pauseWhenHidden）', async () => {
    const poll = vi.fn().mockResolvedValue({ status: 'pending' })
    const wrapper = mount(SsoQrLoginPanel, {
      props: { providers: PROVIDERS, source: makeSource({ poll }), pauseWhenHidden: true },
    })
    await flushPromises()
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(30_000)
    expect(poll).not.toHaveBeenCalled()
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(2000)
    expect(poll).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('props 变化驱动组合式装配（providers / ready / options / source）', async () => {
    const wrapper = mount(SsoQrLoginPanel, { props: { providers: [], source: makeSource(), ready: false } })
    await flushPromises()
    expect(wrapper.find('[data-test="sso-qr-empty"]').exists()).toBe(true)

    await wrapper.setProps({ providers: PROVIDERS, ready: true })
    await flushPromises()
    expect(wrapper.find('[data-test="qr-code"]').exists()).toBe(true)

    await wrapper.setProps({ pollInterval: 3000, backoffMax: 20_000, maxFailures: 2, pauseWhenHidden: false })
    await flushPromises()

    await wrapper.setProps({ source: makeSource({ init: vi.fn().mockRejectedValue(new Error('x')) }) })
    await flushPromises()
    expect(wrapper.findComponent(SsoQrLoginPanel).exists()).toBe(true)
    wrapper.unmount()
  })
})
