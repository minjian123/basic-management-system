// kiwi_id: 2238
/** 模块注入上下文消费用例（只读快照 + 宿主页实体标识取自路由参数 + 经 api 调用后端契约）。 */

import { describe, expect, it } from 'vitest'

import type { ModuleApi, ServiceKey } from '@bms/core'

import slotSampleModule from '../src/index'
import { applyHostContext, currentEntityId, slotSampleRuntime } from '../src/runtime'
import {
  ModuleApiUnavailableError,
  createUserExtension,
  listUserExtensions,
  updateUserExtension,
} from '../src/services/user-extension-service'

/** 请求能力探针（记录调用；按方法返回固定载荷）。 */
class ProbeApi implements ModuleApi {
  /** 调用记录（`<方法>:<服务>:<路径>`）。 */
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
   */
  async get<T>(service: ServiceKey, path = ''): Promise<T> {
    this.calls.push(`get:${service}:${path}`)
    this.assertAlive()
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
    this.assertAlive()
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
    this.assertAlive()
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

  /** 模拟失败。 */
  private assertAlive(): void {
    if (this.fail) {
      throw new Error('探针：请求失败')
    }
  }
}

/**
 * 注入含具名插槽上下文的宿主快照（`api` + 只读 `router`）。
 *
 * @param api 请求能力探针。
 * @param id 路由参数 `id`（宿主页作用实体标识）。
 */
function injectHost(api: ModuleApi, id = '1001'): void {
  applyHostContext({ api, router: { currentRoute: { value: { params: { id } } } } })
}

describe('模块注入上下文消费（Kiwi 2238）', () => {
  it('空上下文自行降级：权限码为空、实体标识为空串（不假定存在）', () => {
    slotSampleModule.setup({})

    expect(slotSampleRuntime()).toEqual({ permissionCount: 0 })
    expect(currentEntityId()).toBe('')
  })

  it('宿主页实体标识取自注入 router 的路由参数（只读消费）', () => {
    applyHostContext({ router: { currentRoute: { value: { params: { id: 2002 } } } } })

    expect(currentEntityId()).toBe('2002')
  })

  it('权限码按只读快照计数', () => {
    slotSampleModule.setup({ user: ['sys:user-extension:query', 'sys:user-extension:update'] })

    expect(slotSampleRuntime()).toEqual({ permissionCount: 2 })
  })

  it('未注入请求能力：调用即抛错（调用方降级，不假定存在）', async () => {
    applyHostContext({})

    await expect(listUserExtensions('1001')).rejects.toThrow(ModuleApiUnavailableError)
  })

  it('经注入 api 按「服务键 + 资源子路径」读写（读列表 / 新增 / 更新）', async () => {
    const probe = new ProbeApi()
    probe.items = [{ id: '1', label: 'vip' }]
    injectHost(probe)

    await expect(listUserExtensions('1001')).resolves.toEqual([{ id: '1', label: 'vip' }])
    await createUserExtension({ userId: '1001', label: 'vip', remark: null })
    await updateUserExtension('1', { label: 'svip', remark: '备注' })

    expect(probe.calls).toEqual([
      'get:platform:/user-extensions',
      'post:platform:/user-extensions',
      'put:platform:/user-extensions/1',
    ])
  })

  it('请求失败（含会话失效）：错误向上传播，由区域件降级（模块无 401 逻辑）', async () => {
    const probe = new ProbeApi()
    probe.fail = true
    injectHost(probe)

    await expect(listUserExtensions('1001')).rejects.toThrow('探针：请求失败')
  })
})
