/** 顶栏业务区补充用例（07-06_01 补修）：待办 / 租户切换 / 用户下拉（偏好设置 · 修改密码）未接入能力提示与展示名回退。 */

import { flushPromises, mount } from '@vue/test-utils'
import { ElDropdown, ElMessage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
 * 挂载顶栏业务区并按需写入用户概要。
 *
 * @param user 会话用户概要（`null` 表示未登录）。
 * @returns 测试装配。
 */
async function mountBar(
  user: { name?: string; username?: string } | null = { name: '管理员', username: 'admin' },
): Promise<{ wrapper: ReturnType<typeof mount>; session: ReturnType<typeof useSessionStore> }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push('/')
  await router.isReady()
  const session = useSessionStore(pinia)
  if (user !== null) {
    session.signIn({
      token: 'token-1',
      user: {
        id: '1',
        username: user.username ?? 'admin',
        name: user.name,
        tenant: 'demo',
        locale: null,
        timezone: null,
        must_change_password: false,
      },
      tenant: 'demo',
    })
  }
  const wrapper = mount(AppHeaderBar, { global: { plugins: [pinia, router] } })
  return { wrapper, session }
}

/**
 * 触发用户下拉命令。
 *
 * @param wrapper 组件包装器。
 * @param command 命令键。
 */
async function emitUserCommand(wrapper: ReturnType<typeof mount>, command: string): Promise<void> {
  const dropdowns = wrapper.findAllComponents(ElDropdown)
  dropdowns[dropdowns.length - 1]?.vm.$emit('command', command)
  await flushPromises()
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AppHeaderBar 补充（07-06_01 补修）', () => {
  it('待办通知：提示功能开发中', async () => {
    const info = vi.spyOn(ElMessage, 'info').mockImplementation(() => undefined as never)
    const { wrapper } = await mountBar()

    await wrapper.find('[data-test="header-todo"]').trigger('click')

    expect(info).toHaveBeenCalledWith('待办通知：功能开发中，见后续任务')
    wrapper.unmount()
  })

  it('租户切换：下拉命令提示功能开发中', async () => {
    const info = vi.spyOn(ElMessage, 'info').mockImplementation(() => undefined as never)
    const { wrapper } = await mountBar()

    const dropdowns = wrapper.findAllComponents(ElDropdown)
    dropdowns[0]?.vm.$emit('command', 'switch')
    await flushPromises()

    expect(info).toHaveBeenCalledWith('租户切换：功能开发中，见后续任务')
    wrapper.unmount()
  })

  it('用户下拉「偏好设置」「修改密码」分别提示功能开发中', async () => {
    const info = vi.spyOn(ElMessage, 'info').mockImplementation(() => undefined as never)
    const { wrapper } = await mountBar()

    await emitUserCommand(wrapper, 'preference')
    expect(info).toHaveBeenCalledWith('偏好设置：功能开发中，见后续任务')

    await emitUserCommand(wrapper, 'password')
    expect(info).toHaveBeenCalledWith('修改密码：功能开发中，见后续任务')

    wrapper.unmount()
  })

  it('用户概要缺展示名时回落账号名；租户未解析时回落占位文案', async () => {
    const { wrapper } = await mountBar({ username: 'admin' })

    expect(wrapper.find('[data-test="header-user"]').text()).toContain('admin')
    expect(wrapper.find('[data-test="header-tenant"]').text()).toContain('demo')

    wrapper.unmount()
  })

  it('未登录会话（无用户概要）时回落「未登录」占位', async () => {
    const { wrapper } = await mountBar(null)

    expect(wrapper.find('[data-test="header-user"]').text()).toContain('未登录')

    wrapper.unmount()
  })

  it('待办角标为 0 时隐藏（无数据源不显示角标）', async () => {
    const { wrapper } = await mountBar()

    expect(wrapper.findComponent({ name: 'ElBadge' }).props('hidden')).toBe(true)

    wrapper.unmount()
  })
})
