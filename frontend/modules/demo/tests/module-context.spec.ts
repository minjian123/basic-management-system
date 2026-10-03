// kiwi_id: 2236
/** 演示模块注入上下文消费用例（只读快照 + 缺失降级 + 宿主请求能力；需求 05-5 / 06-2）。 */

import { describe, expect, it } from 'vitest'

import demoModule from '../src/index'
import { demoRuntime, loadHostUserSummary } from '../src/runtime'

import type { ModuleApi, ModuleRegistration, ServiceKey } from '@bms/core'

/** 请求能力探针（记录调用；可指定返回概要或失败）。 */
class ProbeApi implements ModuleApi {
  /** 调用记录（`<服务>:<路径>`）。 */
  calls: string[] = []

  /**
   * 构造探针。
   *
   * @param summary 返回的概要（`undefined` 视为未使用）。
   * @param fail 是否模拟失败。
   */
  constructor(private readonly summary: unknown = { name: '张三' }, private readonly fail = false) {}

  /**
   * GET 探针（记录调用并返回固定概要）。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   */
  async get<T>(service: ServiceKey, path = ''): Promise<T> {
    this.calls.push(`${service}:${path}`)
    if (this.fail) {
      throw new Error('探针：请求失败')
    }
    return this.summary as T
  }

  /** 未使用的写方法。 */
  async post<T>(): Promise<T> {
    throw new Error('探针：未使用的方法')
  }

  /** 未使用的写方法。 */
  async put<T>(): Promise<T> {
    throw new Error('探针：未使用的方法')
  }

  /** 未使用的写方法。 */
  async del<T>(): Promise<T> {
    throw new Error('探针：未使用的方法')
  }

  /** 未使用的逃生口。 */
  async request<T>(): Promise<T> {
    throw new Error('探针：未使用的方法')
  }
}

/**
 * 取中文文案包的问候文案。
 *
 * @param registration 模块注册声明。
 * @returns 问候文案（缺省空串）。
 */
function zhHello(registration: ModuleRegistration): string {
  const pack = registration.i18nPacks?.find((item) => item.key === 'demo:zh-cn')
  return pack?.messages['demo.hello'] ?? ''
}

describe('演示模块注入上下文消费（Kiwi 980 / 2236）', () => {
  it('经 setup(context) 只读消费宿主能力：上下文缺失时自行降级', () => {
    expect(zhHello(demoModule.setup({}))).toBe('你好，演示模块')
    expect(demoRuntime()).toEqual({ permissionCount: 0 })
  })

  it('上下文存在时按只读快照消费（不直连宿主 store / router）', () => {
    const registration = demoModule.setup({ user: ['sys:user:list', 'sys:user:add'] })
    expect(zhHello(registration)).toBe('你好，已接入 2 项权限')
    expect(demoRuntime()).toEqual({ permissionCount: 2 })
  })

  it('未注入请求能力：不解引用、降级返回 undefined', async () => {
    demoModule.setup({ user: [] })
    await expect(loadHostUserSummary()).resolves.toBeUndefined()
  })

  it('注入请求能力：经 api 按服务键 + 路径取当前用户概要', async () => {
    const probe = new ProbeApi()
    demoModule.setup({ api: probe })

    await expect(loadHostUserSummary()).resolves.toEqual({ name: '张三' })
    expect(probe.calls).toEqual(['identity:/auth/me'])
  })

  it('请求失败（含会话失效）：错误向上传播，由页面降级（模块无 401 逻辑）', async () => {
    const probe = new ProbeApi(undefined, true)
    demoModule.setup({ api: probe })

    await expect(loadHostUserSummary()).rejects.toThrow('探针：请求失败')
  })
})
