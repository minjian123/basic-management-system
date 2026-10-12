// kiwi_id: 2277
/**
 * 占位页用例（02_02 · Kiwi 2277）：未接后端的页面建设中占位——路由元信息标题透传、
 * 标题缺省回退「页面建设中」、路径呈现与空状态件外观。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import PlaceholderView from '@/views/PlaceholderView.vue'

/**
 * 构造携带目标路由的实例。
 *
 * @param meta 路由元信息。
 * @param path 目标路径。
 * @returns 路由实例。
 */
async function makeRouter(meta: Record<string, unknown> | undefined, path = '/placeholder'): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path, name: 'Placeholder', component: { template: '<div />' }, meta },
    ],
  })
  await router.push(path)
  await router.isReady()
  return router
}

/**
 * 挂载占位页。
 *
 * @param meta 路由元信息。
 * @param path 目标路径。
 * @returns 挂载结果（包装器与路由）。
 */
async function mountView(meta: Record<string, unknown> | undefined, path = '/placeholder') {
  const router = await makeRouter(meta, path)
  const wrapper = mount(PlaceholderView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('PlaceholderView（02_02）', () => {
  it('渲染目标路由标题与「页面建设中」路径提示', async () => {
    const { wrapper } = await mountView({ title: '用户管理' }, '/sys/users')

    expect(wrapper.find('.placeholder-page').exists()).toBe(true)
    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('用户管理')
    expect(wrapper.text()).toContain('页面建设中：/sys/users')
  })

  it('路由元信息缺省标题：回退「页面建设中」', async () => {
    const { wrapper } = await mountView(undefined)

    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('页面建设中')
    expect(wrapper.text()).toContain('页面建设中：/placeholder')
  })
})
