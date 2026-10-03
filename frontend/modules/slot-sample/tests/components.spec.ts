// kiwi_id: 2238
/** 区域件渲染与交互用例（jsdom + @vue/test-utils）：列表加载、写操作经注入 api、缺失上下文降级。 */

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ModuleApi, ServiceKey } from '@bms/core'
import { DataTable } from '@bms/ui-ep'

import SlotExtensionDetailTab from '../src/components/SlotExtensionDetailTab.vue'
import SlotExtensionTab from '../src/components/SlotExtensionTab.vue'
import { applyHostContext } from '../src/runtime'

/** 请求能力探针（记录调用；读返回固定行列表、写回显请求体）。 */
class ProbeApi implements ModuleApi {
  /** 调用记录（`<方法>:<服务>:<路径>:<user_id>`）。 */
  calls: string[] = []
  /** `get` 返回的行列表。 */
  items: unknown[] = []
  /** 是否模拟失败。 */
  fail = false

  /**
   * GET 探针。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param params 查询参数。
   */
  async get<T>(service: ServiceKey, path = '', params?: Record<string, unknown>): Promise<T> {
    this.calls.push(`get:${service}:${path}:${String(params?.user_id ?? '')}`)
    if (this.fail) {
      throw new Error('探针：请求失败')
    }
    return { items: this.items } as T
  }

  /**
   * POST 探针。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param data 请求体。
   */
  async post<T>(service: ServiceKey, path = '', data?: unknown): Promise<T> {
    this.calls.push(`post:${service}:${path}`)
    return data as T
  }

  /**
   * PUT 探针。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param data 请求体。
   */
  async put<T>(service: ServiceKey, path = '', data?: unknown): Promise<T> {
    this.calls.push(`put:${service}:${path}`)
    return data as T
  }

  /** 未使用的删除方法。 */
  async del<T>(): Promise<T> {
    throw new Error('探针：未使用的方法')
  }

  /** 未使用的逃生口。 */
  async request<T>(): Promise<T> {
    throw new Error('探针：未使用的方法')
  }
}

/** 扩展信息行 fixture。 */
function row(label: string): Record<string, unknown> {
  return { id: '1', user_id: '1001', label, remark: null, created_at: '', updated_at: '' }
}

/**
 * 注入宿主快照（`api` + 只读 `router`）。
 *
 * @param api 请求能力探针。
 * @param params 路由参数（宿主页作用实体标识）。
 */
function injectHost(api: ModuleApi, params: Record<string, unknown> = { id: '1001' }): void {
  applyHostContext({ api, router: { currentRoute: { value: { params } } } })
}

describe('具名插槽区域件（Kiwi 2238）', () => {
  it('按宿主页实体标识经 api 读列表并渲染行', async () => {
    const probe = new ProbeApi()
    probe.items = [row('vip')]
    injectHost(probe)

    const wrapper = mount(SlotExtensionTab)
    await flushPromises()

    expect(probe.calls).toEqual(['get:platform:/user-extensions:1001'])
    expect(wrapper.text()).toContain('vip')
  })

  it('新增扩展信息经 api 写入并刷新列表', async () => {
    const probe = new ProbeApi()
    injectHost(probe)

    const wrapper = mount(SlotExtensionTab)
    await flushPromises()

    await wrapper.find('[data-test="slot-extension-create"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="slot-extension-editor"]').exists()).toBe(true)

    await wrapper.find('[data-test="slot-extension-label"]').setValue('vip')
    await wrapper.find('[data-test="slot-extension-save"]').trigger('click')
    await flushPromises()

    expect(probe.calls).toEqual([
      'get:platform:/user-extensions:1001',
      'post:platform:/user-extensions',
      'get:platform:/user-extensions:1001',
    ])
  })

  it('双击行进入编辑态并提交更新', async () => {
    const probe = new ProbeApi()
    probe.items = [row('vip')]
    injectHost(probe)

    const wrapper = mount(SlotExtensionTab)
    await flushPromises()

    wrapper.findComponent(DataTable).vm.$emit('row-dblclick', { id: '1', label: 'vip', remark: null })
    await flushPromises()
    expect(wrapper.find('[data-test="slot-extension-editor"]').exists()).toBe(true)

    await wrapper.find('[data-test="slot-extension-remark"]').setValue('重要客户')
    await wrapper.find('[data-test="slot-extension-save"]').trigger('click')
    await flushPromises()

    expect(probe.calls).toContain('put:platform:/user-extensions/1')
  })

  it('宿主页未提供实体标识：降级提示且不发起请求', async () => {
    const probe = new ProbeApi()
    injectHost(probe, {})

    const wrapper = mount(SlotExtensionTab)
    await flushPromises()

    expect(probe.calls).toEqual([])
    expect(wrapper.find('[data-test="slot-extension-no-entity"]').exists()).toBe(true)
  })

  it('未注入请求能力：呈现错误态（模块降级，不抛未捕获异常）', async () => {
    applyHostContext({ router: { currentRoute: { value: { params: { id: '1001' } } } } })

    const wrapper = mount(SlotExtensionTab)
    await flushPromises()

    expect(wrapper.find('[data-test="error"]').text()).toContain('宿主未注入请求能力')
  })

  it('明细件只读渲染列表（权限显隐由区域项声明承担，不进组件）', async () => {
    const probe = new ProbeApi()
    probe.items = [row('vip')]
    injectHost(probe)

    const wrapper = mount(SlotExtensionDetailTab)
    await flushPromises()

    expect(wrapper.text()).toContain('vip')
    expect(probe.calls).toEqual(['get:platform:/user-extensions:1001'])
  })
})
