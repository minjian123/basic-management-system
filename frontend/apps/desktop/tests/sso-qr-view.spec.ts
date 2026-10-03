// kiwi_id: 2233
/** 扫码登录页用例（05_04）：可扫码源过滤 / 空态 / 确认完成（跳转 / 安全回跳）/ 返回保留回跳。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { SsoQrLoginPanel } from '@bms/ui-ep'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setTenantCode } from '@/api/tenant'
import { useSessionStore } from '@/stores/session'
import { redirectTo } from '@/utils/navigation'
import QrLoginView from '@/views/QrLoginView.vue'

vi.mock('qrcode', () => ({
  default: {
    toDataURL: vi.fn(async () => 'data:image/png;base64,MOCKQR'),
  },
}))

vi.mock('@/utils/navigation', () => ({ redirectTo: vi.fn() }))

/** 桩请求适配器。 */
const requestMock = vi.fn()

/** 可扫码 + 非可扫码入口清单。 */
const PROVIDERS = {
  items: [
    { idp_key: 'keycloak', name: 'Keycloak', icon: '', type: 'oidc', sort: 10 },
    { idp_key: 'wecom-1', name: '企业微信', icon: '', type: 'wecom', sort: 20 },
  ],
}

/**
 * 装配桩请求响应。
 *
 * @param providers 入口清单响应。
 */
function stubRequests(providers: unknown = PROVIDERS): void {
  requestMock.mockImplementation((config: RequestConfig) => {
    if (config.url.includes('/auth/sso/providers')) {
      return Promise.resolve(providers)
    }
    if (config.url.includes('/authorize-url')) {
      return Promise.resolve({ authorize_url: 'https://idp/authorize', state: 's1', expires_in: 300 })
    }
    return Promise.resolve(undefined)
  })
}

/** 构造最小路由。 */
function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'Login', component: { template: '<div />' } },
      { path: '/login/qr', name: 'QrLogin', component: { template: '<div />' } },
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', name: 'NotFound', component: { template: '<div />' } },
    ],
  })
}

/**
 * 挂载扫码登录页。
 *
 * @param query 附加查询串。
 * @param providers 入口清单响应。
 * @returns 装配结果。
 */
async function mountQr(
  query = '',
  providers: unknown = PROVIDERS,
): Promise<{ wrapper: ReturnType<typeof mount>; router: Router; pinia: Pinia }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push(query === '' ? '/login/qr' : `/login/qr?${query}`)
  await router.isReady()
  stubRequests(providers)
  const wrapper = mount(QrLoginView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router, pinia }
}

beforeEach(() => {
  requestMock.mockReset()
  configureRequestAdapter({ request: requestMock })
  setTenantCode(null)
  vi.mocked(redirectTo).mockReset()
})

describe('扫码登录页（Kiwi 2233）', () => {
  it('过滤可扫码入口并渲染面板与二维码', async () => {
    const { wrapper } = await mountQr()
    const panel = wrapper.findComponent(SsoQrLoginPanel)
    expect(panel.exists()).toBe(true)
    const passed = panel.props('providers') as { idp_key: string }[]
    expect(passed.map((item) => item.idp_key)).toEqual(['wecom-1'])
    expect(wrapper.find('[data-test="qr-code"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('无可扫码入口渲染空态', async () => {
    const { wrapper } = await mountQr('', { items: [{ idp_key: 'keycloak', name: 'Keycloak', icon: '', type: 'oidc', sort: 1 }] })
    expect(wrapper.find('[data-test="sso-qr-empty"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('确认带 redirect 时顶层跳转', async () => {
    const { wrapper } = await mountQr()
    wrapper.findComponent(SsoQrLoginPanel).vm.$emit('confirmed', { redirect: '/done' })
    await flushPromises()
    expect(redirectTo).toHaveBeenCalledWith('/done')
    wrapper.unmount()
  })

  it('确认无 redirect 时会话就绪后安全回跳（非法 / 缺失回首页）', async () => {
    const { wrapper, router, pinia } = await mountQr('redirect=https%3A%2F%2Fevil.example.com')
    useSessionStore(pinia).applyToken('token-1')
    wrapper.findComponent(SsoQrLoginPanel).vm.$emit('confirmed', {})
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
    wrapper.unmount()
  })

  it('确认无 redirect 且回跳目标合法时回跳原目标', async () => {
    const { wrapper, router, pinia } = await mountQr('redirect=%2Forg%2Fusers')
    useSessionStore(pinia).applyToken('token-1')
    wrapper.findComponent(SsoQrLoginPanel).vm.$emit('confirmed', {})
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/org/users')
    wrapper.unmount()
  })

  it('返回账号登录保留回跳目标', async () => {
    const { wrapper, router } = await mountQr('redirect=%2Forg%2Fusers')
    await wrapper.find('[data-test="sso-qr-back"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/org/users')
    wrapper.unmount()
  })
})
