// kiwi_id: 2236
/** 模块请求能力基类与契约面用例（06_02）：服务键 + 路径寻址 / 幂等键实现点 / 未注入占位 / 非法服务键。 */

import { describe, expect, it } from 'vitest'

import { BaseModuleApi, ErrorCodes, configureRequestAdapter, serviceUrl } from '../src'

import type { RequestAdapter, RequestConfig, ServiceKey } from '../src'

/** 测试用请求能力实现（幂等键口径固定，便于断言实现点被调用）。 */
class ProbeModuleApi extends BaseModuleApi {
  /**
   * 幂等键（探针口径）。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   */
  createIdempotencyKey(service: ServiceKey, path: string): string {
    return `probe:${service}:${path}`
  }
}

/**
 * 记录调用的适配器（返回固定载荷）。
 *
 * @returns `{ configs, adapter }`。
 */
function recordingAdapter(): { configs: RequestConfig[]; adapter: RequestAdapter } {
  const configs: RequestConfig[] = []
  const adapter: RequestAdapter = {
    request<T>(config: RequestConfig): Promise<T> {
      configs.push(config)
      return Promise.resolve({ ok: true } as unknown as T)
    },
  }
  return { configs, adapter }
}

describe('模块请求能力基类（06_02）', () => {
  it('未注入请求适配器时抛 NOT_IMPLEMENTED（占位零请求）', async () => {
    const api = new ProbeModuleApi()
    await expect(api.get('identity', '/auth/me')).rejects.toMatchObject({ code: ErrorCodes.NOT_IMPLEMENTED })
  })

  it('能力键与占位状态：identifier 为 module-api、就绪缺省为真', () => {
    const api = new ProbeModuleApi()
    expect(api.identifier).toBe('module-api')
    expect(api.ready).toBe(true)
  })

  it('get 按服务键 + 路径组装地址（前缀来自单一来源），无幂等键', async () => {
    const { configs, adapter } = recordingAdapter()
    configureRequestAdapter(adapter)

    const result = await new ProbeModuleApi().get('identity', '/auth/me', { withProfile: true })

    expect(result).toEqual({ ok: true })
    expect(configs).toEqual([
      {
        method: 'GET',
        url: serviceUrl('identity', '/auth/me'),
        params: { withProfile: true },
        data: undefined,
        headers: undefined,
        idempotencyKey: undefined,
      },
    ])
  })

  it('post / put 自动带幂等键（口径由宿主实现点提供）', async () => {
    const { configs, adapter } = recordingAdapter()
    configureRequestAdapter(adapter)
    const api = new ProbeModuleApi()

    await api.post('file', '/files', { name: '张三' })
    await api.put('file', '/files/f1', { name: '李四' })

    expect(configs[0]).toMatchObject({
      method: 'POST',
      url: serviceUrl('file', '/files'),
      data: { name: '张三' },
      idempotencyKey: 'probe:file:/files',
    })
    expect(configs[1]).toMatchObject({ method: 'PUT', idempotencyKey: 'probe:file:/files/f1' })
  })

  it('del 带查询参数、无幂等键', async () => {
    const { configs, adapter } = recordingAdapter()
    configureRequestAdapter(adapter)

    await new ProbeModuleApi().del('file', '/files/f1', { force: true })

    expect(configs[0]).toMatchObject({ method: 'DELETE', url: serviceUrl('file', '/files/f1'), params: { force: true } })
    expect(configs[0]?.idempotencyKey).toBeUndefined()
  })

  it('request 逃生口：方法 / 头部 / 显式幂等键原样透传，缺省路径取服务前缀', async () => {
    const { configs, adapter } = recordingAdapter()
    configureRequestAdapter(adapter)

    await new ProbeModuleApi().request({
      method: 'PATCH',
      service: 'platform',
      headers: { 'X-Trace': 't1' },
      idempotencyKey: 'k1',
      data: { enabled: true },
    })

    expect(configs[0]).toEqual({
      method: 'PATCH',
      url: serviceUrl('platform'),
      params: undefined,
      data: { enabled: true },
      headers: { 'X-Trace': 't1' },
      idempotencyKey: 'k1',
    })
  })

  it('非法服务键抛 CAPABILITY_VIOLATION（不静默放行、不发请求）', async () => {
    const { configs, adapter } = recordingAdapter()
    configureRequestAdapter(adapter)

    await expect(new ProbeModuleApi().get('unknown' as ServiceKey)).rejects.toMatchObject({
      code: ErrorCodes.CAPABILITY_VIOLATION,
    })
    expect(configs).toEqual([])
  })
})
