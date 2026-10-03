// kiwi_id: 2236
/** 样例模块注入上下文消费用例（只读快照 + 缺失降级 + 宿主请求能力；需求 05-5 / 06-2）。 */

import { describe, expect, it } from 'vitest'

import sampleModule from '../src/index'
import { SAMPLE_EDIT_PERMISSION, loadHostUserSummary, sampleRuntime } from '../src/runtime'

import type { ModuleApi, ServiceKey } from '@bms/core'

/** 请求能力探针（记录调用；可指定返回概要或失败）。 */
class ProbeApi implements ModuleApi {
  /** 调用记录（`<服务>:<路径>`）。 */
  calls: string[] = []

  /**
   * 构造探针。
   *
   * @param summary 返回的概要。
   * @param fail 是否模拟失败。
   */
  constructor(private readonly summary: unknown = { name: '李四' }, private readonly fail = false) {}

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

describe('样例模块注入上下文消费（Kiwi 982 / 2236）', () => {
  it('空上下文自行降级：无权限信息时按可编辑（样例演示口径）', () => {
    sampleModule.setup({})
    expect(sampleRuntime()).toEqual({ permissionCount: 0, canEdit: true })
  })

  it('按只读快照消费权限码：无编辑权限时降级只读', () => {
    sampleModule.setup({ user: ['sample:record:view'] })
    expect(sampleRuntime()).toEqual({ permissionCount: 1, canEdit: false })
  })

  it('命中编辑权限码时可编辑', () => {
    sampleModule.setup({ user: ['sample:record:view', SAMPLE_EDIT_PERMISSION] })
    expect(sampleRuntime()).toEqual({ permissionCount: 2, canEdit: true })
  })

  it('未注入请求能力：不解引用、降级返回 undefined', async () => {
    sampleModule.setup({})
    await expect(loadHostUserSummary()).resolves.toBeUndefined()
  })

  it('注入请求能力：经 api 按服务键 + 路径取当前用户概要', async () => {
    const probe = new ProbeApi()
    sampleModule.setup({ api: probe })

    await expect(loadHostUserSummary()).resolves.toEqual({ name: '李四' })
    expect(probe.calls).toEqual(['identity:/auth/me'])
  })

  it('请求失败（含会话失效）：错误向上传播，由页面降级（模块无 401 逻辑）', async () => {
    const probe = new ProbeApi(undefined, true)
    sampleModule.setup({ api: probe })

    await expect(loadHostUserSummary()).rejects.toThrow('探针：请求失败')
  })
})
