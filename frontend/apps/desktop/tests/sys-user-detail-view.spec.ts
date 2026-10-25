// kiwi_id: 2276
/** 用户详情宿主页用例（02_02/_01）：具名插槽挂接位声明 / 路由参数注入 / 会话权限码透传。 */

import { ModuleAreaOutlet, PageContainer, SectionContainer } from '@bms/ui_ep'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { installPlatformRegistrations } from '@/module/host'
import { registries, registriesRevision } from '@/module/registries'
import { useSessionStore } from '@/stores/session'
import SysUserDetailView from '@/views/SysUserDetailView.vue'

/** 具名插槽标识（与源码同口径）。 */
const USER_DETAIL_TABS = 'sys.user.detail.tabs'

/**
 * 构造用户详情路由（携带路由参数 `id`）。
 *
 * @param id 用户标识。
 * @returns 路由实例。
 */
async function makeRouter(id = '7'): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/sys/users/:id', name: 'SysUserDetail', component: { template: '<div />' } },
    ],
  })
  await router.push(`/sys/users/${id}`)
  await router.isReady()
  return router
}

/**
 * 挂载用户详情宿主页。
 *
 * @param options 路由参数与权限码。
 * @returns 装配结果。
 */
async function mountDetail(options: { id?: string; codes?: string[] } = {}): Promise<{
  wrapper: ReturnType<typeof mount>
  pinia: Pinia
  router: Router
}> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = await makeRouter(options.id ?? '7')
  const session = useSessionStore(pinia)
  session.setCodes(options.codes ?? [])
  const wrapper = mount(SysUserDetailView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, pinia, router }
}

beforeEach(() => {
  // 装配状态跨用例复位：注册表与装配版本号回到空 / 零。
  for (const key of registries.pageArea.keys()) {
    registries.pageArea.unregister(key)
  }
  registriesRevision.value = 0
})

describe('用户详情宿主页（02_02/_01）', () => {
  it('声明单个 tabs 形态具名插槽挂接位并透传注册表与版本号', async () => {
    const { wrapper } = await mountDetail()

    const outlet = wrapper.findComponent(ModuleAreaOutlet)
    expect(outlet.exists()).toBe(true)
    expect(outlet.props('area')).toBe(USER_DETAIL_TABS)
    expect(outlet.props('variant')).toBe('tabs')
    expect(outlet.props('registries')).toBe(registries)
    expect(outlet.props('revision')).toBe(0)

    wrapper.unmount()
  })

  it('路由参数注入容器描述，权限码跟随会话', async () => {
    const { wrapper } = await mountDetail({ id: '42', codes: ['user:assign_role'] })

    const container = wrapper.findComponent(PageContainer)
    expect(container.props('title')).toBe('用户详情')
    expect(container.props('description')).toBe('用户标识：42')
    expect(wrapper.findComponent(SectionContainer).props('title')).toBe('扩展信息')

    const outlet = wrapper.findComponent(ModuleAreaOutlet)
    expect(outlet.props('permissionCodes')).toEqual(['user:assign_role'])

    wrapper.unmount()
  })

  it('路由缺少 id 参数时描述回落空串', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/detail', name: 'Detail', component: { template: '<div />' } },
        { path: '/', name: 'Home', component: { template: '<div />' } },
      ],
    })
    await router.push('/detail')
    await router.isReady()
    const wrapper = mount(SysUserDetailView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.findComponent(PageContainer).props('description')).toBe('用户标识：')

    wrapper.unmount()
  })

  it('区域项按权限显隐：持权限渲染页签，未持权限空区域不兜底', async () => {
    installPlatformRegistrations()

    const granted = await mountDetail({ id: '7', codes: ['user:assign_role'] })
    expect(granted.wrapper.find('[data-variant="tabs"]').exists()).toBe(true)
    expect(granted.wrapper.text()).toContain('角色分配')
    granted.wrapper.unmount()

    const denied = await mountDetail({ id: '7', codes: [] })
    expect(denied.wrapper.text()).not.toContain('角色分配')
    denied.wrapper.unmount()
  })
})
