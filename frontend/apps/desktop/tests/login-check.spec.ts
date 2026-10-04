// kiwi_id: 2232, 2240
/** 登录页核对页用例（05_01 / 05_06）：三组自检程序化跑通、页面渲染无失败项。 */

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { describe, expect, it } from 'vitest'

import LoginCheck from '@/dev/LoginCheck.vue'

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
})
