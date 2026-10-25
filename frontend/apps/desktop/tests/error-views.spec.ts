/** 状态错误页用例（04-1-1）：403 / 404 / 500 复用组件库错误页，操作事件接线到路由（首页 / 返回 / 重试）。 */

import { ErrorPage } from '@bms/ui_ep'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import ForbiddenView from '@/views/ForbiddenView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import ServerErrorView from '@/views/ServerErrorView.vue'

/**
 * 构造最小路由并落在 `/500`（错误页操作只依赖 `$router`，路径本身不参与判定）。
 *
 * @returns 路由实例。
 */
async function makeRouter(): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/403', name: 'Forbidden', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', name: 'NotFound', component: { template: '<div />' } },
    ],
  })
  await router.push('/500')
  await router.isReady()
  return router
}

/**
 * 挂载状态错误页。
 *
 * @param component 错误页组件。
 * @returns 组件包装器。
 */
async function mountView(component: typeof ForbiddenView): Promise<VueWrapper> {
  const router = await makeRouter()
  return mount(component, { global: { plugins: [router] } })
}

describe('状态错误页（04-1-1）', () => {
  it('403 页渲染「无访问权限」并复用错误页外观', async () => {
    const wrapper = await mountView(ForbiddenView)
    const page = wrapper.findComponent(ErrorPage)
    expect(page.exists()).toBe(true)
    expect(page.props('code')).toBe(403)
    expect(wrapper.find('main.status-page').exists()).toBe(true)
    expect(wrapper.find('[data-test="error-code"]').text()).toBe('403')
    expect(wrapper.text()).toContain('无访问权限')
    wrapper.unmount()
  })

  it('404 页渲染「页面不存在」', async () => {
    const wrapper = await mountView(NotFoundView)
    const page = wrapper.findComponent(ErrorPage)
    expect(page.exists()).toBe(true)
    expect(page.props('code')).toBe(404)
    expect(wrapper.find('[data-test="error-code"]').text()).toBe('404')
    expect(wrapper.text()).toContain('页面不存在')
    expect(wrapper.find('[data-test="error-retry"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('500 页渲染「服务异常」并暴露重试入口', async () => {
    const wrapper = await mountView(ServerErrorView)
    const page = wrapper.findComponent(ErrorPage)
    expect(page.exists()).toBe(true)
    expect(page.props('code')).toBe(500)
    expect(wrapper.find('[data-test="error-code"]').text()).toBe('500')
    expect(wrapper.find('[data-test="error-retry"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('403 页「返回首页」推送到首页、「返回上一页」回退', async () => {
    const wrapper = await mountView(ForbiddenView)
    const router = wrapper.vm.$router as Router
    const push = vi.spyOn(router, 'push')
    const back = vi.spyOn(router, 'back')

    await wrapper.find('[data-test="error-home"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')

    await wrapper.find('[data-test="error-back"]').trigger('click')
    await flushPromises()
    expect(back).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('404 页「返回首页」「返回上一页」接线到路由', async () => {
    const wrapper = await mountView(NotFoundView)
    const router = wrapper.vm.$router as Router
    const push = vi.spyOn(router, 'push')
    const back = vi.spyOn(router, 'back')

    await wrapper.find('[data-test="error-home"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')

    await wrapper.find('[data-test="error-back"]').trigger('click')
    await flushPromises()
    expect(back).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('500 页三操作（首页 / 返回 / 重试）接线到路由', async () => {
    const wrapper = await mountView(ServerErrorView)
    const router = wrapper.vm.$router as Router
    const push = vi.spyOn(router, 'push')
    const back = vi.spyOn(router, 'back')
    const go = vi.spyOn(router, 'go')

    await wrapper.find('[data-test="error-home"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')

    await wrapper.find('[data-test="error-back"]').trigger('click')
    await flushPromises()
    expect(back).toHaveBeenCalledTimes(1)

    await wrapper.find('[data-test="error-retry"]').trigger('click')
    await flushPromises()
    expect(go).toHaveBeenCalledWith(0)

    wrapper.unmount()
  })
})
