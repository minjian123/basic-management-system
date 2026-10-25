// kiwi_id: 2190, 2231, 2232, 2233
/** 兜底分支用例（模块桩 / 桩数据驱动）：登录页与三张开发态核对页的 `??` 回落与「未通过」渲染分支。 */

import { configureRequestAdapter } from '@bms/core'
import { CaptchaField } from '@bms/ui_ep'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import AuthGuardCheck from '@/dev/AuthGuardCheck.vue'
import LoginCheck from '@/dev/LoginCheck.vue'
import SsoQrCheck from '@/dev/SsoQrCheck.vue'
import LoginView from '@/views/LoginView.vue'

vi.mock('@/utils/login', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/login')>()
  return {
    ...actual,
    // 形态判定契约外取值（`undefined`）：驱动登录页模板 `captchaKind ?? 'image'` 兜底。
    pickLoginCaptchaKind: (() => undefined) as unknown as typeof actual.pickLoginCaptchaKind,
    // 滑块凭证缺轨迹：驱动核对页标签 `sliderCredential.trace ?? []` 兜底。
    toLoginCaptcha: ((credential: Parameters<typeof actual.toLoginCaptcha>[0]) => {
      const payload = actual.toLoginCaptcha(credential)
      delete payload.trace
      return payload
    }) as typeof actual.toLoginCaptcha,
  }
})

vi.mock('@bms/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@bms/core')>()
  return {
    ...actual,
    // 跳登录地址缺省 `query`（契约外取值）：驱动守卫核对页标签「redirect=无」兜底并构造未通过项。
    buildLoginLocation: ((path: string, options?: Parameters<typeof actual.buildLoginLocation>[1]) => {
      const location = actual.buildLoginLocation(path, options)
      delete location.query
      return location
    }) as typeof actual.buildLoginLocation,
    // 可扫码身份源为空：构造扫码核对页未通过项（模板「未通过」分支）。
    selectScannableProviders: (() => []) as unknown as typeof actual.selectScannableProviders,
  }
})

/**
 * 构造登录页最小路由。
 *
 * @returns 路由实例。
 */
function makeRouter(): ReturnType<typeof createRouter> {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/login', name: 'Login', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', name: 'NotFound', component: { template: '<div />' } },
    ],
  })
}

/**
 * 轮询等待条件成立（挂载期异步落定，避免定时竞态）。
 *
 * @param predicate 条件。
 * @param timeout 超时毫秒数。
 * @returns 条件成立或超时。
 */
async function waitFor(predicate: () => boolean, timeout = 2000): Promise<void> {
  const deadline = Date.now() + timeout
  while (!predicate() && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 5))
  }
}

describe('兜底分支（模块桩驱动）', () => {
  it('验证码形态不可判定：登录页模板回落图形码并渲染验证码块', async () => {
    // 策略强制 + 数据源返回挑战：验证码块渲染，形态经模板兜底为图形码。
    vi.stubGlobal(
      'fetch',
      vi.fn((input: unknown) => {
        const url = String(input)
        const data = url.includes('/policy')
          ? { scene: 'login', required: true, fail_threshold: 3, ttl: 300, cooldown: 60, channels: ['image'] }
          : {
              captcha_id: 'c1',
              kind: 'image',
              image: '',
              expires_in: 300,
              scene: 'login',
              payload: JSON.stringify({ background: 'AAAA', slider: 'BBBB', width: 300, height: 150 }),
              target: '',
              cooldown: 0,
            }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ code: 0, message: 'ok', data }) })
      }),
    )
    configureRequestAdapter({ request: async () => ({ items: [] }) })

    const router = makeRouter()
    await router.push('/login')
    const wrapper = mount(LoginView, { global: { plugins: [createPinia(), router] } })
    await waitFor(() => wrapper.find('[data-test="login-captcha"]').exists())

    expect(wrapper.find('[data-test="login-captcha"]').exists()).toBe(true)
    expect(wrapper.findComponent(CaptchaField).props('kind')).toBe('image')

    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('滑块凭证缺轨迹：核对页标签回落空序列并按未通过上屏', async () => {
    const router = makeRouter()
    await router.push('/login')
    const wrapper = mount(LoginCheck, { global: { plugins: [createPinia(), router] } })
    await waitFor(() => wrapper.findAll('[data-check]').length === 20)

    const item = wrapper.findAll('[data-check]').find((node) => node.text().includes('凭证归一'))
    expect(item?.attributes('data-ok')).toBe('false')
    expect(item?.text()).toContain('[]')
  })

  it('跳登录地址缺省 query：守卫核对页渲染「未通过」', () => {
    const wrapper = mount(AuthGuardCheck)

    const failed = wrapper.findAll('[data-ok="false"]')
    expect(failed).toHaveLength(1)
    expect(failed[0]?.text()).toContain('无')
    expect(failed[0]?.text()).toContain('未通过')
    expect(wrapper.find('[data-check-passed]').text()).toBe('19')
  })

  it('可扫码身份源为空：扫码核对页渲染「未通过」', () => {
    const wrapper = mount(SsoQrCheck)

    const failed = wrapper.findAll('[data-ok="false"]')
    expect(failed).toHaveLength(1)
    expect(failed[0]?.text()).toContain('未通过')
    expect(wrapper.find('[data-check-passed]').text()).toBe(String(wrapper.findAll('[data-check]').length - 1))
  })
})
