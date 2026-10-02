// kiwi_id: 2232
/** 登录页用例（05_01）：表单提交与回跳 / 验证码时机 / SSO 入口 / 错误文案 / 密码安全口径。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/error'
import { setTenantCode } from '@/api/tenant'
import { useSessionStore } from '@/stores/session'
import { notifyMustChangePassword } from '@/utils/feedback'
import { redirectTo } from '@/utils/navigation'
import LoginView from '@/views/LoginView.vue'

vi.mock('@/utils/feedback', () => ({
  MUST_CHANGE_PASSWORD_MESSAGE: '请尽快修改初始密码',
  SESSION_EXPIRED_MESSAGE: '登录状态已失效，请重新登录',
  notifyMustChangePassword: vi.fn(),
  notifySessionExpired: vi.fn(),
}))

vi.mock('@/utils/navigation', () => ({ redirectTo: vi.fn() }))

/** 桩请求适配器。 */
const requestMock = vi.fn()

/** 桩登录成功响应（契约 `LoginResult`）。 */
const LOGIN_SUCCESS = {
  access_token: 'token-1',
  expires_in: 1800,
  token_type: 'Bearer',
  user: {
    id: '1',
    username: 'admin',
    name: '管理员',
    tenant: 'acme',
    locale: null,
    timezone: null,
    must_change_password: false,
  },
}

/** 桩 SSO 入口清单（排序值乱序，验证渲染排序）。 */
const SSO_PROVIDERS = {
  items: [
    { idp_key: 'dingtalk', name: '钉钉', icon: '', type: 'dingtalk', sort: 20 },
    { idp_key: 'keycloak', name: 'Keycloak', icon: '', type: 'oidc', sort: 10 },
  ],
}

/** 登录页测试装配。 */
interface Harness {
  /** 组件包装器。 */
  wrapper: VueWrapper
  /** 路由实例。 */
  router: Router
  /** Pinia 实例。 */
  pinia: Pinia
}

/**
 * 构造最小路由。
 *
 * @returns 路由实例。
 */
function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'Login', component: { template: '<div />' } },
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', name: 'NotFound', component: { template: '<div />' } },
    ],
  })
}

/**
 * 桩验证码数据源响应（HTTP 内建数据源走全局 `fetch`）。
 *
 * @param policy 策略覆盖项。
 */
function stubCaptchaFetch(policy: { required?: boolean; channels?: string[] } = {}): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: unknown) => {
      const url = String(input)
      const data = url.includes('/policy')
        ? {
            scene: 'login',
            required: policy.required ?? false,
            fail_threshold: 3,
            ttl: 300,
            cooldown: 60,
            channels: policy.channels ?? ['slider', 'image'],
          }
        : {
            captcha_id: 'c1',
            kind: 'slider',
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
}

/**
 * 装配桩请求适配器响应（SSO 清单 / 登录分派）。
 *
 * @param options 分派覆盖项。
 */
function stubRequests(options: { login?: () => unknown; providers?: unknown } = {}): void {
  requestMock.mockImplementation((config: RequestConfig) => {
    if (config.url.includes('/auth/sso/providers')) {
      return Promise.resolve(options.providers ?? { items: [] })
    }
    if (config.url.includes('/auth/login')) {
      const factory = options.login
      if (factory === undefined) {
        return Promise.reject(new ApiError(20002, '账号或密码错误'))
      }
      try {
        return Promise.resolve(factory())
      } catch (error) {
        return Promise.reject(error)
      }
    }
    return Promise.resolve(undefined)
  })
}

/**
 * 挂载登录页。
 *
 * @param query 附加查询串（如 `redirect=%2Forg%2Fusers`）。
 * @returns 测试装配。
 */
async function mountLogin(query = ''): Promise<Harness> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push(query === '' ? '/login' : `/login?${query}`)
  await router.isReady()
  const wrapper = mount(LoginView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router, pinia }
}

/**
 * 取密码输入元素。
 *
 * `data-test` 落点差异：`TextInput` 根元素即 Element Plus 输入框（非 class/style 属性透传到内部原生
 * `input`，故 `[data-test="login-account"]` 命中 input）；`PasswordInput` 根元素是包装 div（`data-test`
 * 落在 div 上，须再取内部 `input`）。
 *
 * @param wrapper 组件包装器。
 * @returns 密码原生 input 包装器。
 */
function passwordField(wrapper: VueWrapper): DOMWrapper<Element> {
  return wrapper.find('[data-test="login-password"] input')
}

/**
 * 填写账号口令并提交表单。
 *
 * @param wrapper 组件包装器。
 * @param account 账号。
 * @param password 口令。
 */
async function submit(wrapper: VueWrapper, account = 'admin', password = 'secret'): Promise<void> {
  await wrapper.find('[data-test="login-account"]').setValue(account)
  await passwordField(wrapper).setValue(password)
  await wrapper.find('[data-test="login-form"]').trigger('submit')
  await flushPromises()
}

/** 登录请求次数。 */
function loginCalls(): RequestConfig[] {
  return requestMock.mock.calls
    .map((call) => call[0] as RequestConfig)
    .filter((config) => config.url.includes('/auth/login'))
}

beforeEach(() => {
  setTenantCode(null)
  window.localStorage.clear()
  requestMock.mockReset()
  stubRequests()
  stubCaptchaFetch()
  configureRequestAdapter({ request: requestMock })
  vi.mocked(redirectTo).mockClear()
  vi.mocked(notifyMustChangePassword).mockClear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('登录页（Kiwi 2232）', () => {
  it('提交成功：载荷含归一租户、写入会话并按 redirect 回跳', async () => {
    stubRequests({ login: () => LOGIN_SUCCESS })
    const { wrapper, router, pinia } = await mountLogin(`redirect=${encodeURIComponent('/org/users?page=2')}`)

    await wrapper.find('[data-test="login-tenant"]').setValue(' acme ')
    await submit(wrapper)

    expect(loginCalls()).toHaveLength(1)
    expect(loginCalls()[0]?.data).toEqual({
      account: 'admin',
      password: 'secret',
      tenant: 'acme',
    })

    const session = useSessionStore(pinia)
    expect(session.token).toBe('token-1')
    expect(session.user?.name).toBe('管理员')
    expect(session.tenant).toBe('acme')
    expect(router.currentRoute.value.fullPath).toBe('/org/users?page=2')
  })

  it('非法 redirect 回落首页（站内校验沿用核心单一来源）', async () => {
    stubRequests({ login: () => LOGIN_SUCCESS })
    const { wrapper, router } = await mountLogin(`redirect=${encodeURIComponent('https://evil.example.com/x')}`)

    await submit(wrapper)

    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('提交中态防重复：连点两次只发一次登录请求', async () => {
    let release: (() => void) | undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    stubRequests({ login: () => gate.then(() => LOGIN_SUCCESS) })
    const { wrapper } = await mountLogin()

    await wrapper.find('[data-test="login-account"]').setValue('admin')
    await passwordField(wrapper).setValue('secret')
    const form = wrapper.find('[data-test="login-form"]')
    await form.trigger('submit')
    await form.trigger('submit')
    release?.()
    await flushPromises()

    expect(loginCalls()).toHaveLength(1)
  })

  it('本地校验：账号或口令为空不发请求', async () => {
    const { wrapper } = await mountLogin()

    await wrapper.find('[data-test="login-form"]').trigger('submit')
    await flushPromises()

    expect(loginCalls()).toHaveLength(0)
    expect(wrapper.find('[data-test="login-error"]').text()).toContain('请填写账号与密码')
  })

  it('验证码块：策略未强制且未失败不显示；策略 required 时初始显示', async () => {
    const normal = await mountLogin()
    expect(normal.wrapper.find('[data-test="login-captcha"]').exists()).toBe(false)
    normal.wrapper.unmount()

    stubCaptchaFetch({ required: true, channels: ['image'] })
    const forced = await mountLogin()
    expect(forced.wrapper.find('[data-test="login-captcha"]').exists()).toBe(true)
  })

  it('验证码块：首次登录失败后显示并强制；凭证未完备时不再发请求', async () => {
    const { wrapper } = await mountLogin()

    await submit(wrapper)
    expect(wrapper.find('[data-test="login-error"]').text()).toContain('账号或密码错误')
    expect(wrapper.find('[data-test="login-captcha"]').exists()).toBe(true)
    expect(loginCalls()).toHaveLength(1)

    await submit(wrapper)
    expect(loginCalls()).toHaveLength(1)
    expect(wrapper.find('[data-test="login-error"]').text()).toContain('请完成验证码校验')
  })

  it('验证码强制后：图形码凭证随登录请求一次性提交（延迟提交模式）', async () => {
    stubCaptchaFetch({ required: true, channels: ['image'] })
    stubRequests({ login: () => LOGIN_SUCCESS })
    const { wrapper } = await mountLogin()

    await wrapper.find('[data-test="login-account"]').setValue('admin')
    await passwordField(wrapper).setValue('secret')
    await wrapper.find('[data-test="captcha-input"]').setValue('ab12')
    await wrapper.find('[data-test="login-form"]').trigger('submit')
    await flushPromises()

    expect(loginCalls()).toHaveLength(1)
    expect(loginCalls()[0]?.data).toMatchObject({
      account: 'admin',
      captcha: { captcha_id: 'c1', kind: 'image', code: 'ab12' },
    })
  })

  it('验证码强制但未填写时不发请求（本地拦截，零校验请求）', async () => {
    stubCaptchaFetch({ required: true, channels: ['image'] })
    const { wrapper } = await mountLogin()

    await submit(wrapper)

    expect(loginCalls()).toHaveLength(0)
    expect(wrapper.find('[data-test="login-error"]').text()).toContain('请完成验证码校验')
  })

  it('错误文案取核心文案表：账号锁定 / 验证码错误 / 外部登录不可用', async () => {
    const locked = await mountLogin()
    stubRequests({
      login: () => {
        throw new ApiError(20003, 'locked')
      },
    })
    await submit(locked.wrapper)
    expect(locked.wrapper.find('[data-test="login-error"]').text()).toContain('账号已锁定')
    locked.wrapper.unmount()

    const captcha = await mountLogin()
    stubRequests({
      login: () => {
        throw new ApiError(20101, 'captcha')
      },
    })
    await submit(captcha.wrapper)
    expect(captcha.wrapper.find('[data-test="login-error"]').text()).toContain('验证码错误')
    captcha.wrapper.unmount()

    const sso = await mountLogin('error=20053&message=idp%20down')
    expect(sso.wrapper.find('[data-test="login-error"]').text()).toContain('外部登录服务不可用')
  })

  it('SSO 回调失败无对应文案时回落 message', async () => {
    const { wrapper } = await mountLogin('error=99999&message=自定义失败信息')

    expect(wrapper.find('[data-test="login-error"]').text()).toContain('自定义失败信息')
  })

  it('SSO 入口：清单为空不渲染；有清单按 sort 升序渲染且点击顶层跳转', async () => {
    const empty = await mountLogin()
    expect(empty.wrapper.find('[data-test="login-sso"]').exists()).toBe(false)
    empty.wrapper.unmount()

    stubRequests({ providers: SSO_PROVIDERS })
    const { wrapper } = await mountLogin()

    const items = wrapper.findAll('[data-test="login-sso-item"]')
    expect(items.map((item) => item.text())).toEqual(['Keycloak', '钉钉'])

    await items[0]?.trigger('click')
    expect(vi.mocked(redirectTo)).toHaveBeenCalledWith('/api/identity/v1/auth/sso/keycloak/authorize')
  })

  it('密码安全口径：类型 / 初值 / 自动填充语义，且无「记住我」与强度提示', async () => {
    const { wrapper } = await mountLogin()
    const password = passwordField(wrapper)

    expect(password.attributes('type')).toBe('password')
    expect((password.element as HTMLInputElement).value).toBe('')
    expect(password.attributes('autocomplete')).toBe('new-password')
    expect(wrapper.find('[data-test="password-strength"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('记住我')
    expect(wrapper.text()).not.toContain('强度')
  })

  it('明文切换由组件库件提供：图标仅在填写后出现，切换只改输入类型（仅内存态、不发请求）', async () => {
    const { wrapper } = await mountLogin()
    const password = passwordField(wrapper)
    const toggleSelector = '[data-test="login-password"] .el-input__password'

    // Element Plus 明文切换图标仅在有值时渲染（`showPwdVisible` 依赖当前值非空）。
    expect(wrapper.find(toggleSelector).exists()).toBe(false)

    await password.setValue('secret')
    const toggle = wrapper.find(toggleSelector)
    expect(toggle.exists()).toBe(true)

    await toggle.trigger('click')
    expect(password.attributes('type')).toBe('text')

    await toggle.trigger('click')
    expect(password.attributes('type')).toBe('password')
    expect(loginCalls()).toHaveLength(0)
  })

  it('表单件复用口径：输入件为组件库件、按钮为 Element Plus 件（无裸原生件自绘）', async () => {
    const { wrapper } = await mountLogin()

    expect(wrapper.findAll('.bms-text-input')).toHaveLength(2)
    expect(wrapper.findAll('.bms-password-input')).toHaveLength(1)
    expect(wrapper.find('[data-test="login-submit"]').classes()).toContain('el-button')

    const nakedInputs = wrapper
      .findAll('input')
      .filter((input) => input.element.closest('.bms-text-input, .bms-password-input') === null)
    const nakedButtons = wrapper.findAll('button').filter((button) => !button.classes().includes('el-button'))
    expect(nakedInputs).toHaveLength(0)
    expect(nakedButtons).toHaveLength(0)
  })

  it('强制改密标记为真时提示「请尽快修改初始密码」', async () => {
    stubRequests({
      login: () => ({ ...LOGIN_SUCCESS, user: { ...LOGIN_SUCCESS.user, must_change_password: true } }),
    })
    const { wrapper } = await mountLogin()

    await submit(wrapper)

    expect(vi.mocked(notifyMustChangePassword)).toHaveBeenCalledTimes(1)
  })
})
