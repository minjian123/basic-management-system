// kiwi_id: 2232, 2240
/** 登录页核对页用例（05_01 / 05_06）：三组自检程序化跑通、页面渲染无失败项。 */

import { request } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { describe, expect, it } from 'vitest'

import LoginCheck from '@/dev/LoginCheck.vue'
import LoginView from '@/views/LoginView.vue'

/**
 * 构造核对页最小路由（登录页挂载需要）。
 *
 * @returns 路由实例。
 */
function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'HomeView', component: { template: '<div />' } },
      { path: '/login', name: 'Login', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', name: 'NotFound', component: { template: '<div />' } },
    ],
  })
}

/**
 * 等待核对页挂载期异步（两次 `flush`、桩提交与重渲染）落定。
 *
 * @param ms 等待毫秒数。
 * @returns 等待完成。
 */
function wait(ms = 10): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * 轮询等待条件成立（覆盖率插桩下挂载期异步更慢，避免定时竞态）。
 *
 * @param predicate 条件。
 * @param timeout 超时毫秒数。
 * @returns 条件成立或超时。
 */
async function waitFor(predicate: () => boolean, timeout = 2000): Promise<void> {
  const deadline = Date.now() + timeout
  while (!predicate() && Date.now() < deadline) {
    await wait(5)
  }
}

describe('登录页核对页（Kiwi 2232）', () => {
  it('渲染三组自检且全部通过（无失败项）', async () => {
    const router = makeRouter()
    await router.push('/login')
    const wrapper = mount(LoginCheck, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    await flushPromises()
    await flushPromises()

    expect(wrapper.findAll('[data-check-group]')).toHaveLength(3)

    const items = wrapper.findAll('[data-check]')
    expect(items).toHaveLength(20)

    const failed = wrapper.findAll('[data-ok="false"]')
    expect(failed.map((item) => item.text())).toEqual([])

    expect(wrapper.find('[data-check-passed]').text()).toBe('20')
  })

  it('含验证码延迟提交与登录接线口径说明', async () => {
    const router = makeRouter()
    await router.push('/login')
    const wrapper = mount(LoginCheck, { global: { plugins: [createPinia(), router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('验证码时机与延迟提交说明')
    expect(wrapper.text()).toContain('登录接线口径')
    expect(wrapper.find('[data-test="login-host"]').exists()).toBe(true)
  })

  it('查询根缺失 / 桩适配器未命中：判空回落分支跑通，未通过项如实上屏', async () => {
    const router = makeRouter()
    await router.push('/login')
    const wrapper = mount(LoginCheck, { global: { plugins: [createPinia(), router] } })
    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, unknown> } }).$.setupState

    // 查询根置空：驱动 `pick` / `fillInput` / 宿主守卫的判空回落。
    state.host = null
    // 首个桩适配器未命中 SSO 清单 → else 返回 undefined。
    await request({ method: 'GET', url: '/api/identity/v1/self-check' })
    // `20007` 桩适配器未命中登录 → else 返回 undefined（挂载期两次 `flush` 后已换桩）。
    await waitFor(() => (state.groups as unknown[]).length === 3)
    await request({ method: 'GET', url: '/api/identity/v1/self-check-else' })
    await waitFor(() => wrapper.findAll('[data-check]').length === 20)

    expect(wrapper.findAll('[data-check]')).toHaveLength(20)
    const failed = wrapper.findAll('[data-ok="false"]')
    expect(failed.length).toBeGreaterThan(0)
    expect(failed.every((item) => item.text().includes('未通过'))).toBe(true)
    expect(wrapper.find('[data-check-passed]').text()).toBe(String(20 - failed.length))
  })

  it('口令在结构自检读取前已非空：密码安全口径按「非空」上屏（未通过）', async () => {
    const router = makeRouter()
    await router.push('/login')
    const wrapper = mount(LoginCheck, { global: { plugins: [createPinia(), router] } })

    // 页面结构自检读取口令初值前写入被核对页的口令：驱动「初值非空」分支。
    const loginView = wrapper.findComponent(LoginView)
    const loginState = (loginView.vm as unknown as { $: { setupState: Record<string, unknown> } }).$.setupState
    loginState.password = 'secret'
    // 双保险：直接写 DOM 初值（自检按 DOM 读取），避免重渲染时序竞态。
    const passwordInput = wrapper.find('[data-test="login-password"] input').element as HTMLInputElement
    passwordInput.value = 'secret'
    await waitFor(() => wrapper.findAll('[data-check]').length === 20)

    const item = wrapper.findAll('[data-check]').find((node) => node.text().includes('密码安全口径'))
    expect(item?.attributes('data-ok')).toBe('false')
    expect(item?.text()).toContain('非空')
  })

  it('入口首项文本 / 宿主文本缺省：模板兜底分支跑通，未通过项如实上屏', async () => {
    const router = makeRouter()
    await router.push('/login')
    const wrapper = mount(LoginCheck, { global: { plugins: [createPinia(), router] } })
    const host = wrapper.find('[data-test="login-host"]').element as HTMLElement

    // 桩数据缺口一：入口列表长度为 1 但首项文本为 `null`（契约外取值）→ `textContent ?? ''` 兜底。
    const originalQuerySelectorAll = host.querySelectorAll.bind(host)
    host.querySelectorAll = ((selector: string) => {
      if (selector === '[data-test="login-sso-item"]') {
        return [{ textContent: null }] as unknown as NodeListOf<Element>
      }
      return originalQuerySelectorAll(selector)
    }) as typeof host.querySelectorAll
    // 桩数据缺口二：宿主文本为 `null`（契约外取值）→ 页面文本兜底（`20007` 项按未通过上屏）。
    Object.defineProperty(host, 'textContent', { configurable: true, get: () => null, set: () => undefined })

    await waitFor(() => wrapper.findAll('[data-check]').length === 20)

    const failed = wrapper.findAll('[data-ok="false"]').map((item) => item.text())
    expect(failed.some((text) => text.includes('SSO 入口按清单渲染'))).toBe(true)
    expect(failed.some((text) => text.includes('20007 展开租户标识输入框'))).toBe(true)
  })
})
