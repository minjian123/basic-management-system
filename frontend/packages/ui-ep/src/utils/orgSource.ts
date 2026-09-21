/**
 * 组织数据源：HTTP 内建实现 + 注册表默认实例（`fetch` 单一落点）。
 *
 * 端点与后端组织主数据出口同源（`/api/v1/org/users|posts|dept-tree|resolve-names`）；
 * 宿主可经 `registerOrgSource` 登记定制实现（如组织 store 版）或覆盖内建键。
 */

import {
  BaseError,
  BaseOrgSource,
  OrgSourceProvider,
  OrgSourceRegistry,
  buildOrgResolveQuery,
  buildOrgSearchQuery,
  type OrgDeptTreeQuery,
  type OrgKind,
  type OrgPostQuery,
  type OrgResolveQuery,
  type OrgSourceOptions,
  type OrgUserQuery,
} from '@bms/core'

/** 链路内默认组织数据源注册表实例（宿主可登记定制实现或覆盖内建键）。 */
export const orgSourceRegistry = new OrgSourceRegistry()

/**
 * 登记组织数据源实现。
 *
 * @param key 数据源键（同键拒重）。
 * @param create 数据源工厂。
 */
export function registerOrgSource(
  key: string,
  create: (options: OrgSourceOptions) => BaseOrgSource | Promise<BaseOrgSource>,
): void {
  orgSourceRegistry.register(new OrgSourceProvider(key, create))
}

/** HTTP 内建组织数据源（未覆盖的方法不请求）。 */
class HttpOrgSource extends BaseOrgSource {
  /** 实现名。 */
  override readonly pluginName: string = 'http'
  /** 装载选项（端点 / 请求头）。 */
  readonly #options: OrgSourceOptions

  /**
   * 构造 HTTP 数据源。
   *
   * @param options 装载选项。
   */
  constructor(options: OrgSourceOptions = {}) {
    super()
    this.#options = options
  }

  /**
   * 用户查询。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async searchUsers(query: OrgUserQuery): Promise<unknown> {
    return this.#get('/org/users', this.#searchParams('user', query))
  }

  /**
   * 岗位查询。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async searchPosts(query: OrgPostQuery): Promise<unknown> {
    return this.#get('/org/posts', this.#searchParams('post', query))
  }

  /**
   * 部门树查询。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async loadDeptTree(query: OrgDeptTreeQuery): Promise<unknown> {
    return this.#get('/org/dept-tree', query.status === undefined || query.status === '' ? {} : { status: query.status })
  }

  /**
   * 批量回显。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async resolveNames(query: OrgResolveQuery): Promise<unknown> {
    return this.#get('/org/resolve-names', buildOrgResolveQuery(query.target, query.ids))
  }

  /**
   * 线参数构造（查询出口；与后端同源）。
   *
   * @param kind 对象类型。
   * @param query 查询入参。
   */
  #searchParams(kind: OrgKind, query: OrgUserQuery | OrgPostQuery): Record<string, unknown> {
    return buildOrgSearchQuery({
      kind,
      keyword: query.keyword,
      deptId: query.deptId,
      includeChildren: query.includeChildren,
      status: query.status,
      page: query.page,
      pageSize: query.pageSize,
    })
  }

  /**
   * GET 请求并解统一响应包装。
   *
   * @param path 路径（相对端点前缀）。
   * @param params 查询参数。
   * @returns 数据体（无 `fetch` 能力时降级 `undefined`）。
   */
  async #get(path: string, params: Record<string, unknown>): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      return undefined
    }
    const endpoint = (this.#options.endpoint ?? '/api/v1').replace(/\/+$/, '')
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '' || value === false) {
        continue
      }
      search.set(key, value === true ? 'true' : String(value))
    }
    const query = search.size > 0 ? `?${search.toString()}` : ''
    const headers = typeof this.#options.headers === 'function' ? this.#options.headers() : this.#options.headers
    const response = await fetchFn(`${endpoint}${path}${query}`, { method: 'GET', headers })
    if (!response.ok) {
      throw new BaseError(30101, '组织数据源不可用')
    }
    return unwrapResponse(await response.json())
  }
}

/**
 * 创建 HTTP 内建组织数据源。
 *
 * @param options 装载选项。
 * @returns 数据源实例。
 */
export function createHttpOrgSource(options: OrgSourceOptions = {}): BaseOrgSource {
  return new HttpOrgSource(options)
}

/** 登记内建 HTTP 数据源（默认键，宿主可覆盖）。 */
registerOrgSource('http', createHttpOrgSource)

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
