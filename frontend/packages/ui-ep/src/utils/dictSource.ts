/**
 * 字典数据源：HTTP 内建实现 + 注册表默认实例（`fetch` 单一落点）。
 *
 * 端点与后端字典出口同源（`/api/v1/dicts/{type}`、`/dicts/batch`、`/dicts/{type}/attrs`、
 * `/dicts/query-providers`、`/dicts/{type}/advanced-query`、`/query-schemes`）；
 * 宿主可经 `registerDictSource` 登记定制实现（如宿主 store 版）或覆盖内建键。
 */

import {
  BaseDictSource,
  BaseError,
  DictSourceProvider,
  DictSourceRegistry,
  buildDictAdvQuery,
  buildDictBatchQuery,
  buildDictTypeQuery,
  type DictQueryScheme,
  type DictSourceAdvQuery,
  type DictSourceAttrsQuery,
  type DictSourceBatchQuery,
  type DictSourceOptions,
  type DictSourceProvidersQuery,
  type DictSourceSchemeQuery,
  type DictSourceTypeQuery,
} from '@bms/core'

/** 链路内默认字典数据源注册表实例（宿主可登记定制实现或覆盖内建键）。 */
export const dictSourceRegistry = new DictSourceRegistry()

/**
 * 登记字典数据源实现。
 *
 * @param key 数据源键（同键拒重）。
 * @param create 数据源工厂。
 */
export function registerDictSource(
  key: string,
  create: (options: DictSourceOptions) => BaseDictSource | Promise<BaseDictSource>,
): void {
  dictSourceRegistry.register(new DictSourceProvider(key, create))
}

/** HTTP 内建字典数据源（未覆盖的方法不请求）。 */
class HttpDictSource extends BaseDictSource {
  /** 实现名。 */
  override readonly pluginName: string = 'http'
  /** 装载选项（端点 / 请求头）。 */
  readonly #options: DictSourceOptions

  /**
   * 构造 HTTP 数据源。
   *
   * @param options 装载选项。
   */
  constructor(options: DictSourceOptions = {}) {
    super()
    this.#options = options
  }

  /**
   * 单类型取数。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async getType(query: DictSourceTypeQuery): Promise<unknown> {
    return this.#request('GET', `/dicts/${encodeURIComponent(query.dictType)}`, buildDictTypeQuery(query))
  }

  /**
   * 批量取数。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async batch(query: DictSourceBatchQuery): Promise<unknown> {
    return this.#request('POST', '/dicts/batch', buildDictBatchQuery(query.types, query.version, query.locale))
  }

  /**
   * 属性 schema。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async loadAttrs(query: DictSourceAttrsQuery): Promise<unknown> {
    return this.#request('GET', `/dicts/${encodeURIComponent(query.dictType)}/attrs`, {
      ...(query.locale === undefined ? {} : { locale: query.locale }),
    })
  }

  /**
   * 查询提供者清单。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async loadProviders(query: DictSourceProvidersQuery): Promise<unknown> {
    return this.#request('GET', '/dicts/query-providers', {
      ...(query.dictType === undefined || query.dictType === '' ? {} : { dict_type: query.dictType }),
    })
  }

  /**
   * 高级查询。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async advancedQuery(query: DictSourceAdvQuery): Promise<unknown> {
    return this.#request(
      'POST',
      `/dicts/${encodeURIComponent(query.dictType)}/advanced-query`,
      buildDictAdvQuery(query.target, {
        conditions: query.conditions,
        provider: query.provider,
        params: query.params,
        page: query.page,
        size: query.size,
      }),
    )
  }

  /**
   * 查询方案清单。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async listSchemes(query: DictSourceSchemeQuery): Promise<unknown> {
    return this.#request('GET', '/query-schemes', this.#schemeParams(query))
  }

  /**
   * 默认方案解析。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async resolveDefaultScheme(query: DictSourceSchemeQuery): Promise<unknown> {
    return this.#request('GET', '/query-schemes/default', this.#schemeParams(query))
  }

  /**
   * 保存方案（新建 / 更新）。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async saveScheme(query: DictSourceSchemeQuery): Promise<unknown> {
    const scheme = query.scheme
    if (scheme === undefined) {
      return undefined
    }
    const body = schemeToWire(scheme)
    if (scheme.id !== undefined) {
      return this.#request('PUT', `/query-schemes/${scheme.id}`, body)
    }
    return this.#request('POST', '/query-schemes', body)
  }

  /**
   * 删除方案。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async deleteScheme(query: DictSourceSchemeQuery): Promise<unknown> {
    if (query.schemeId === undefined) {
      return undefined
    }
    return this.#request('DELETE', `/query-schemes/${query.schemeId}`, {})
  }

  /**
   * 方案查询参数。
   *
   * @param query 查询入参。
   */
  #schemeParams(query: DictSourceSchemeQuery): Record<string, unknown> {
    const params: Record<string, unknown> = { target: query.target }
    if (query.fieldKey !== undefined && query.fieldKey !== '') {
      params.field_key = query.fieldKey
    }
    return params
  }

  /**
   * 统一请求并解响应包装。
   *
   * @param method 方法。
   * @param path 路径（相对端点前缀）。
   * @param payload 查询参数（GET / DELETE）或请求体（POST / PUT）。
   * @returns 数据体（无 `fetch` 能力时降级 `undefined`）。
   */
  async #request(method: 'GET' | 'POST' | 'PUT' | 'DELETE', path: string, payload: Record<string, unknown>): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      return undefined
    }
    const endpoint = (this.#options.endpoint ?? '/api/v1').replace(/\/+$/, '')
    const headers = typeof this.#options.headers === 'function' ? this.#options.headers() : this.#options.headers
    const init: RequestInit = { method, headers: { 'Content-Type': 'application/json', ...(headers ?? {}) } }
    let url = `${endpoint}${path}`
    if (method === 'GET' || method === 'DELETE') {
      const search = new URLSearchParams()
      for (const [key, value] of Object.entries(payload)) {
        if (value === undefined || value === null || value === false) {
          continue
        }
        search.set(key, value === true ? 'true' : String(value))
      }
      url = search.size > 0 ? `${url}?${search.toString()}` : url
    } else {
      init.body = JSON.stringify(payload)
    }
    const response = await fetchFn(url, init)
    if (!response.ok) {
      throw new BaseError(40101, '字典数据源不可用')
    }
    return unwrapResponse(await response.json())
  }
}

/**
 * 创建 HTTP 内建字典数据源。
 *
 * @param options 装载选项。
 * @returns 数据源实例。
 */
export function createHttpDictSource(options: DictSourceOptions = {}): BaseDictSource {
  return new HttpDictSource(options)
}

/** 登记内建 HTTP 数据源（默认键，宿主可覆盖）。 */
registerDictSource('http', createHttpDictSource)

/**
 * 方案 → 线格式（`camelCase` → 后端 `snake_case`）。
 *
 * @param scheme 方案。
 * @returns 请求体。
 */
function schemeToWire(scheme: DictQueryScheme): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: scheme.name,
    scope: scheme.scope,
    target: scheme.target,
    is_default: scheme.isDefault,
    shared: scheme.shared,
    status: 'enabled',
  }
  if (scheme.id !== undefined) {
    body.id = scheme.id
  }
  if (scheme.dictType !== undefined) {
    body.dict_type = scheme.dictType
  }
  if (scheme.providerKey !== undefined) {
    body.provider_key = scheme.providerKey
  }
  if (scheme.conditions !== undefined) {
    body.conditions = scheme.conditions
  }
  if (scheme.params !== undefined) {
    body.params = scheme.params
  }
  return body
}

/**
 * 解统一响应包装（`{ code, message, data }`；非包装原样返回；业务码非 0 / 200 抛错）。
 *
 * @param payload 原始响应体。
 * @returns 数据体。
 */
function unwrapResponse(payload: unknown): unknown {
  if (payload !== null && typeof payload === 'object' && !Array.isArray(payload)) {
    const record = payload as { code?: unknown; message?: unknown; data?: unknown }
    if (typeof record.code === 'number') {
      if (record.code !== 0 && record.code !== 200) {
        throw new BaseError(record.code, typeof record.message === 'string' ? record.message : '')
      }
      return record.data
    }
  }
  return payload
}
