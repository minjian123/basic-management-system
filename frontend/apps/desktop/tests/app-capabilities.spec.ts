// kiwi_id: 2524
/** 宿主能力装配（09_01）：默认源装配 / 幂等 / 未装配报错 / 顶栏铃铛按装配取数。 */

import { flushPromises, mount } from '@vue/test-utils'
import { NoticeBell, NoticeDetail } from '@bms/ui_ep'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getAppCapabilities, installAppCapabilities, resetAppCapabilities } from '@/capabilities'
import AppHeaderBar from '@/components/AppHeaderBar.vue'
import { useSessionStore } from '@/stores/session'

/** 统一响应包装。 */
function wrap(data: unknown): unknown {
  return { code: 0, message: '', data }
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
      { path: '/', name: 'HomeView', component: { template: '<div />' } },
      { path: '/login', name: 'Login', component: { template: '<div />' } },
    ],
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  resetAppCapabilities()
})

describe('宿主能力装配（09_01）', () => {
  it('装配六类默认源且幂等；复位后取用报 19001', () => {
    const first = installAppCapabilities()
    expect(first.dictSource).toBeDefined()
    expect(first.dictRemoteSource).toBeDefined()
    expect(first.uploadTransport).toBeDefined()
    expect(first.captchaSource).toBeDefined()
    expect(first.notificationJobs).toBeDefined()
    expect(first.auditQuery).toBeDefined()
    expect(installAppCapabilities()).toBe(first)
    expect(getAppCapabilities()).toBe(first)

    resetAppCapabilities()
    expect(() => getAppCapabilities()).toThrow()
  })

  it('顶栏铃铛按装配取数（未读校准 + 最近列表）', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('unread-count')) {
        return { ok: true, json: async () => wrap({ count: 2 }) }
      }
      if (url.includes('/notifications/404')) {
        return { ok: true, json: async () => wrap(null) }
      }
      if (/\/notifications\/\d+(\?|$)/.test(url)) {
        return { ok: true, json: async () => wrap({ id: '1', title: '待办 A', content: '详情正文', is_read: true }) }
      }
      return {
        ok: true,
        json: async () =>
          wrap({ list: [{ id: '1', title: '待办 A', type: 'approval', is_read: false }], total: 1 }),
      }
    })
    vi.stubGlobal('fetch', fetchMock)
    installAppCapabilities()

    const pinia = createPinia()
    setActivePinia(pinia)
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    useSessionStore(pinia).signIn({
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
    const wrapper = mount(AppHeaderBar, { global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/notifications/unread-count'))).toBe(true)
    expect(wrapper.find('[data-test="header-notice"]').attributes('data-ready')).toBe('true')
    expect(wrapper.find('[data-test="notice-badge"]').text()).toBe('2')

    // 铃铛事件全链路：打开详情 / 单条已读 / 全部已读 / 查看全部 / 重试 / 详情跳转
    const bell = wrapper.findComponent(NoticeBell)
    bell.vm.$emit('open', { id: '1', title: '待办 A' })
    await flushPromises()
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/notifications/1'))).toBe(true)

    bell.vm.$emit('read-all')
    await flushPromises()
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/notifications/read-all'))).toBe(true)
    bell.vm.$emit('read', '1')
    bell.vm.$emit('view-all')
    bell.vm.$emit('retry')
    await flushPromises()

    bell.vm.$emit('open', { id: '404', title: '已删除' })
    await flushPromises()

    wrapper.findComponent(NoticeDetail).vm.$emit('jump', { bizType: 'wf_task', bizId: '9' })
    wrapper.findComponent(NoticeDetail).vm.$emit('update:modelValue', false)
    await flushPromises()

    wrapper.unmount()
  })
})
