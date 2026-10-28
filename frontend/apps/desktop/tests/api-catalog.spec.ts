// kiwi_id: 2363
/**
 * 平台目录快照适配用例（07B 03_02 · 前端目录消费）：
 * 请求形态、三段映射、四类不可用、失败重试一次、并发共享、令牌变化复位。
 */

import {
  catalogState,
  catalogUnavailableReason,
  configureRequestAdapter,
  derivedServiceKeys,
  productKeys,
  resetCatalog,
  resolveCapabilityEndpoint,
  type RequestAdapter,
  type RequestConfig,
} from '@bms/core'
import { afterEach, describe, expect, it } from 'vitest'

import { ensureProductCatalog, resetProductCatalog } from '@/api/catalog'

/** 合法快照夹具（虚构产品 `demo`：数据源类 + 读出口类能力，含产品分组服务行）。 */
const SNAPSHOT = {
  modules: [
    { module_key: 'platform', service_key: 'platform', service_group: 'foundation', status: 'enabled' },
    { module_key: 'report', service_key: 'report', service_group: 'capability', status: 'enabled' },
    { module_key: 'biz', service_key: 'biz', service_group: 'product', status: 'enabled' },
    { module_key: 'org', service_key: null, service_group: 'product', status: 'enabled' },
  ],
  products: [{ product_key: 'demo', name: '演示产品', status: 'enabled' }],
  collaborations: [
    {
      name: 'demo.org.dept-data',
      domain: 'org',
      kind: 'dataset',
      product_key: 'demo',
      frontend_prefix: 'demo',
      contract_version: '0.1.0',
      status: 'enabled',
      replacement: null,
    },
  ],
  snapshot_version: '2',
  warnings: [],
}

/**
 * 装配请求适配器桩。
 *
 * @param outcomes 依次返回的载荷（`Error` 表示该次请求抛错）。
 * @returns 调用记录与还原函数。
 */
function stubAdapter(...outcomes: (unknown | Error)[]): { configs: RequestConfig[]; restore: () => void } {
  const configs: RequestConfig[] = []
  let index = 0
  const adapter: RequestAdapter = {
    request: <T>(config: RequestConfig): Promise<T> => {
      configs.push(config)
      const outcome = outcomes[Math.min(index, outcomes.length - 1)]
      index += 1
      if (outcome instanceof Error) {
        return Promise.reject(outcome)
      }
      return Promise.resolve(outcome as T)
    },
  }
  configureRequestAdapter(adapter)
  return { configs, restore: () => configureRequestAdapter({ request: () => Promise.reject(new Error('未装配')) }) }
}

afterEach(() => {
  resetProductCatalog()
  resetCatalog()
})

describe('目录装载：请求与映射（07B 03_02）', () => {
  it('成功：请求带参三段，映射产品 / 服务 / 能力并可取址', async () => {
    const { configs } = stubAdapter(SNAPSHOT)

    await expect(ensureProductCatalog()).resolves.toBe('ready')

    expect(configs[0]?.method).toBe('GET')
    expect(configs[0]?.url).toBe('/api/platform/v1/modules/snapshot')
    expect(configs[0]?.params).toEqual({ with: 'modules,products,collaborations' })
    expect(catalogState()).toBe('ready')
    expect(productKeys()).toEqual(['demo'])
    expect(derivedServiceKeys()).toEqual(['platform', 'report'])
    expect(resolveCapabilityEndpoint('org', 'dataset')).toEqual({
      status: 'ok',
      productKey: 'demo',
      frontendPrefix: 'demo',
      endpoint: '/api/demo/v1/demo',
    })
  })

  it('已就绪：再次调用不再请求（幂等）', async () => {
    const { configs } = stubAdapter(SNAPSHOT)

    await ensureProductCatalog()
    await ensureProductCatalog()

    expect(configs).toHaveLength(1)
  })

  it('并发调用共享同一 Promise（只发一次请求）', async () => {
    const { configs } = stubAdapter(SNAPSHOT)

    const [first, second] = await Promise.all([ensureProductCatalog(), ensureProductCatalog()])

    expect(first).toBe('ready')
    expect(second).toBe('ready')
    expect(configs).toHaveLength(1)
  })

  it('首次请求失败 → 立即重试一次并成功', async () => {
    const { configs } = stubAdapter(new Error('网络抖动'), SNAPSHOT)

    await expect(ensureProductCatalog()).resolves.toBe('ready')
    expect(configs).toHaveLength(2)
  })
})

describe('目录装载：四类不可用（07B 03_02）', () => {
  it('两次请求均失败 → request-failed', async () => {
    const { configs } = stubAdapter(new Error('网络断开'))

    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(configs).toHaveLength(2)
    expect(catalogUnavailableReason()).toBe('request-failed')
    expect(productKeys()).toEqual([])
  })

  it('结构不合规（缺段）→ invalid-payload 且不重试', async () => {
    const { configs } = stubAdapter({ modules: [], products: [] })

    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(configs).toHaveLength(1)
    expect(catalogUnavailableReason()).toBe('invalid-payload')
  })

  it('结构不合规（非对象 / 缺版本 / warnings 非数组）→ invalid-payload', async () => {
    stubAdapter(null)
    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('invalid-payload')

    resetProductCatalog()
    stubAdapter({ ...SNAPSHOT, snapshot_version: 2 })
    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('invalid-payload')

    resetProductCatalog()
    stubAdapter({ ...SNAPSHOT, warnings: 'oops' })
    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('invalid-payload')
  })

  it('结构不合规（段内字段形态非法）→ invalid-payload', async () => {
    stubAdapter({ ...SNAPSHOT, products: [{ name: '缺产品键' }] })

    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('invalid-payload')
  })

  it('结构不合规（warnings 非字符串数组）→ invalid-payload', async () => {
    stubAdapter({ ...SNAPSHOT, warnings: [1] })

    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('invalid-payload')
  })

  it('products 为空 → no-products（不把未装载当成无产品）', async () => {
    stubAdapter({ ...SNAPSHOT, products: [] })

    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('no-products')
  })

  it('warnings 非空 → warnings（降级原因可读）', async () => {
    stubAdapter({ ...SNAPSHOT, warnings: ['能力目录为空（产品清单未装载或未声明 [[collaborations]] 段）'] })

    await expect(ensureProductCatalog()).resolves.toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('warnings')
  })
})

describe('目录复位（令牌变化）（07B 03_02）', () => {
  it('复位后状态回 idle，再次调用重新请求', async () => {
    const { configs } = stubAdapter(SNAPSHOT)

    await ensureProductCatalog()
    resetProductCatalog()
    expect(catalogState()).toBe('idle')

    await ensureProductCatalog()
    expect(configs).toHaveLength(2)
  })

  it('复位可打断进行中的装载（在途结果丢弃，后续调用重新发起）', async () => {
    const { configs } = stubAdapter(SNAPSHOT)
    const inFlight = ensureProductCatalog()
    resetProductCatalog()

    await expect(inFlight).resolves.toBe('idle')
    await expect(ensureProductCatalog()).resolves.toBe('ready')

    expect(configs.length).toBeGreaterThanOrEqual(2)
  })
})
