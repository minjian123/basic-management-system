// kiwi_id: 2363
/**
 * 目录端口与取址用例（07B 03_02 · 前端目录消费）：
 * 状态与投影、服务键派生、按「业务域 + 能力种类」取址、四类不可用、零改动夹具。
 */

import { afterEach, describe, expect, it } from 'vitest'

import {
  BaseModuleApi,
  applyCatalogSnapshot,
  catalogState,
  catalogUnavailableReason,
  catalogWarnings,
  configureRequestAdapter,
  derivedServiceKeys,
  markCatalogLoading,
  markCatalogUnavailable,
  productKeys,
  resetCatalog,
  resolveCapabilityEndpoint,
  resolveCapabilityTarget,
  type CatalogSnapshotProjection,
  type RequestAdapter,
  type RequestConfig,
} from '../src'

/** 目录夹具（虚构产品 `demo`：一个数据源类能力 + 一个读出口能力）。 */
const DEMO_PROJECTION: CatalogSnapshotProjection = {
  products: [{ productKey: 'demo', status: 'enabled' }],
  services: [
    { serviceKey: 'platform', serviceGroup: 'foundation', status: 'enabled' },
    { serviceKey: 'report', serviceGroup: 'capability', status: 'enabled' },
    { serviceKey: 'workflow', serviceGroup: 'capability', status: 'planned' },
    { serviceKey: 'biz', serviceGroup: 'product', status: 'enabled' },
    { serviceKey: '', serviceGroup: 'foundation', status: 'enabled' },
    { serviceKey: 'platform', serviceGroup: 'foundation', status: 'enabled' },
  ],
  collaborations: [
    { name: 'demo.org.dept-data', domain: 'org', kind: 'dataset', productKey: 'demo', frontendPrefix: 'demo' },
    { name: 'demo.org.user-roles', domain: 'org', kind: 'read', productKey: 'demo', frontendPrefix: 'demo' },
    { name: 'demo.org.pending', domain: 'org', kind: 'dataset', productKey: null, frontendPrefix: null },
  ],
  warnings: [],
}

afterEach(() => {
  resetCatalog()
})

/**
 * 注入目录夹具。
 *
 * @param projection 目录投影（缺省 `DEMO_PROJECTION`）。
 */
function apply(projection: CatalogSnapshotProjection = DEMO_PROJECTION): void {
  applyCatalogSnapshot(projection)
}

describe('目录状态与投影（07B 03_02）', () => {
  it('初始为 idle：产品键为空、服务键派生为空、无原因与警示', () => {
    expect(catalogState()).toBe('idle')
    expect(productKeys()).toEqual([])
    expect(derivedServiceKeys()).toEqual([])
    expect(catalogUnavailableReason()).toBeNull()
    expect(catalogWarnings()).toEqual([])
  })

  it('装载中只改状态', () => {
    markCatalogLoading()
    expect(catalogState()).toBe('loading')
    expect(productKeys()).toEqual([])
  })

  it('写入投影后 ready，并可复位回 idle', () => {
    apply()
    expect(catalogState()).toBe('ready')
    expect(productKeys()).toEqual(['demo'])
    resetCatalog()
    expect(catalogState()).toBe('idle')
    expect(productKeys()).toEqual([])
  })

  it('不可用：记录原因与警示，投影清空', () => {
    apply()
    markCatalogUnavailable('warnings', ['能力目录为空'])
    expect(catalogState()).toBe('unavailable')
    expect(catalogUnavailableReason()).toBe('warnings')
    expect(catalogWarnings()).toEqual(['能力目录为空'])
    expect(productKeys()).toEqual([])
  })

  it('不可用可无警示（原因仍可取）', () => {
    markCatalogUnavailable('request-failed')
    expect(catalogUnavailableReason()).toBe('request-failed')
    expect(catalogWarnings()).toEqual([])
  })
})

describe('服务键派生（07B 03_02）', () => {
  it('仅取非产品分组、已启用、服务键非空且去重保序', () => {
    apply()
    expect(derivedServiceKeys()).toEqual(['platform', 'report'])
  })
})

describe('按「业务域 + 能力种类」取址（07B 03_02）', () => {
  it('唯一目标：返回产品键与前端域段（忽略同域其它种类与空目标）', () => {
    apply()
    expect(resolveCapabilityTarget('org', 'dataset')).toEqual({
      status: 'ok',
      productKey: 'demo',
      frontendPrefix: 'demo',
    })
  })

  it('同一目标多条能力按 (产品键, 域段) 去重（不误判歧义）', () => {
    apply({
      ...DEMO_PROJECTION,
      collaborations: [
        { name: 'demo.org.dept-data', domain: 'org', kind: 'dataset', productKey: 'demo', frontendPrefix: 'demo' },
        { name: 'demo.org.post-data', domain: 'org', kind: 'dataset', productKey: 'demo', frontendPrefix: 'demo' },
      ],
    })
    expect(resolveCapabilityTarget('org', 'dataset').status).toBe('ok')
  })

  it('目录未就绪 → catalog-unavailable', () => {
    expect(resolveCapabilityTarget('org', 'dataset')).toEqual({ status: 'catalog-unavailable' })
    markCatalogUnavailable('no-products')
    expect(resolveCapabilityTarget('org', 'dataset')).toEqual({ status: 'catalog-unavailable' })
  })

  it('该域无对应种类能力 → capability-missing', () => {
    apply()
    expect(resolveCapabilityTarget('sup', 'dataset')).toEqual({ status: 'capability-missing' })
  })

  it('目标不唯一 → ambiguous（不猜、不挑选）', () => {
    apply({
      ...DEMO_PROJECTION,
      collaborations: [
        { name: 'demo.org.dept-data', domain: 'org', kind: 'dataset', productKey: 'demo', frontendPrefix: 'demo' },
        { name: 'other.org.dept-data', domain: 'org', kind: 'dataset', productKey: 'other', frontendPrefix: 'other' },
      ],
    })
    expect(resolveCapabilityTarget('org', 'dataset')).toEqual({ status: 'ambiguous' })
  })

  it('出口组装：ok 时给出 `/api/{产品键}/v1/{域段}`，其余原样透传状态', () => {
    apply()
    expect(resolveCapabilityEndpoint('org', 'dataset')).toEqual({
      status: 'ok',
      productKey: 'demo',
      frontendPrefix: 'demo',
      endpoint: '/api/demo/v1/demo',
    })
    expect(resolveCapabilityEndpoint('sup', 'dataset')).toEqual({ status: 'capability-missing' })
    resetCatalog()
    expect(resolveCapabilityEndpoint('org', 'dataset')).toEqual({ status: 'catalog-unavailable' })
  })
})

describe('零改动夹具：新增产品无需改前端代码（07B 03_02）', () => {
  /** 探针模块能力（幂等键固定，便于断言）。 */
  class ProbeModuleApi extends BaseModuleApi {
    /**
     * 生成幂等键（探针口径）。
     *
     * @param target 寻址主体。
     * @param path 资源子路径。
     * @returns 固定幂等键。
     */
    createIdempotencyKey(target: string, path: string): string {
      return `probe:${target}:${path}`
    }
  }

  it('虚构产品可被产品键判定、可取址、可经模块能力发请求', async () => {
    const calls: RequestConfig[] = []
    const adapter: RequestAdapter = {
      request: <T>(config: RequestConfig): Promise<T> => {
        calls.push(config)
        return Promise.resolve({ ok: true } as T)
      },
    }
    configureRequestAdapter(adapter)

    apply()
    expect(productKeys()).toContain('demo')
    expect(resolveCapabilityEndpoint('org', 'dataset')).toMatchObject({ endpoint: '/api/demo/v1/demo' })

    await new ProbeModuleApi().product('demo', 'demo').get('/data-source/dept-tree')
    expect(calls[0]?.url).toBe('/api/demo/v1/demo/data-source/dept-tree')
  })
})
