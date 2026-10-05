/** 顶栏业务区用例（07-06_01 补修）：四入口渲染 / 展示名回退 / 用户下拉命令（退出登录）。 */

import { flushPromises, mount } from '@vue/test-utils'
import { ElDropdown } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import AppHeaderBar from '@/components/AppHeaderBar.vue'
import { useSessionStore } from '@/stores/session'

/**
 * 构造最小路由。
 *
 * @returns 路由实例。
 */
function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'HomeView', component: { template: '<div />' } },
      { path: '/login', name: 'Login', component: { template: '<div />' } },
    ],
  })
}

/**
 * 挂载顶栏业务区。
 *
 * @param signedIn 是否写入登录态。
 * @returns 测试装配。
 */
async function mountBar(signedIn = true): Promise<{
  wrapper: ReturnType<typeof mount>
  router: Router
  session: ReturnType<typeof useSessionStore>
}> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push('/')
  await router.isReady()
  const session = useSessionStore(pinia)
  if (signedIn) {
    session.signIn({
      token: 'token-1',
      user: {
        id: '1',
        username: 'admin',
        name: '管理员',
        tenant: 'demo',
        locale: null,
        timezone: null,
        must_change_password: false,
      },
      tenant: 'demo',
    })
  }
  const wrapper = mount(AppHeaderBar, { global: { plugins: [pinia, router] } })
  return { wrapper, router, session }
}

describe('AppHeaderBar（顶栏业务区，07-06_01 补修）', () => {
  it('渲染待办 / 租户 / 用户三入口与展示名', async () => {
    const { wrapper } = await mountBar()

    expect(wrapper.find('[data-test="header-todo"]').text()).toContain('待办')
    expect(wrapper.find('[data-test="header-tenant"]').text()).toContain('demo')
    expect(wrapper.find('[data-test="header-user"]').text()).toContain('管理员')
  })

  it('会话缺失时展示名回退占位（默认租户 / 未登录）', async () => {
    const { wrapper } = await mountBar(false)

    expect(wrapper.find('[data-test="header-tenant"]').text()).toContain('默认租户')
    expect(wrapper.find('[data-test="header-user"]').text()).toContain('未登录')
  })

  it('用户下拉「退出登录」：登出并回登录页', async () => {
    const { wrapper, router, session } = await mountBar()
    const signOut = vi.spyOn(session, 'signOut').mockResolvedValue(undefined)

    const dropdowns = wrapper.findAllComponents(ElDropdown)
    dropdowns[dropdowns.length - 1]?.vm.$emit('command', 'signout')
    await flushPromises()

    expect(signOut).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
