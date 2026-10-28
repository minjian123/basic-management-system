/**
 * 组织数据源：HTTP 内建实现 + 注册表默认实例（`fetch` 单一落点）。
 *
 * 端点**运行期取自平台目录快照**（`03_02`）：按「业务域 `org` + 能力种类 `dataset`」推导提供方产品键与
 * 前端命名空间域段，再经**寻址契约**组装为 `/api/{产品键}/v1/{域段}`——平台代码不持有产品键、不持有
 * 产品命名空间常量。路径为出口口径 `/data-source/{users,posts,dept-tree}` 与 `/resolve-names`
 * （**查询与批量回显分列两个出口**、**部门树一次性返回**）。
 * 目录不可用（或该域无数据源类能力 / 目标不唯一）时端点解析为 `null`：**不发请求**、不拼默认地址，
 * 由消费方进入降级（禁用并提示）。
 * 宿主可经 `registerOrgSource` 登记定制实现（如组织 store 版）或覆盖内建键。
 */

import {
  BaseError,
  BaseOrgSource,
  OrgSourceProvider,
  OrgSourceRegistry,
  buildOrgResolveQuery,
  buildOrgSearchQuery,
  resolveCapabilityEndpoint,
  type OrgDeptTreeQuery,
  type OrgKind,
  type OrgPostQuery,
  type OrgResolveQuery,
  type OrgSourceOptions,
  type OrgUserQuery,
} from '@bms/core'

/** 组织主数据所属**业务域**标识（非产品键；产品改名 / 新增产品不影响本常量）。 */
export const ORG_SOURCE_DOMAIN = 'org'

/** 组织数据源对应的**能力种类**（数据源类能力；同域可能另有读出口与事务分支类）。 */
export const ORG_SOURCE_CAPABILITY_KIND = 'dataset'

/** 降级文案：目录不可用（请求失败 / 结构不合规 / 产品为空 / 有警示）。 */
export const ORG_DEGRADE_UNAVAILABLE_TEXT = '组织数据暂不可用，请稍后重试'

/** 降级文案：目录正常但未登记组织数据源类能力。 */
export const ORG_DEGRADE_NOT_INTEGRATED_TEXT = '未接入组织主数据'

/** 降级文案：同一业务域存在多组数据源目标（不猜、不挑选）。 */
export const ORG_DEGRADE_AMBIGUOUS_TEXT = '组织数据源配置不唯一'

/** 端点缺失告警是否已输出（避免每次取数刷屏）。 */
let endpointWarningEmitted = false

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
    return this.#get('/data-source/users', this.#searchParams('user', query))
  }

  /**
   * 岗位查询。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async searchPosts(query: OrgPostQuery): Promise<unknown> {
    return this.#get('/data-source/posts', this.#searchParams('post', query))
  }

  /**
   * 部门树查询。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async loadDeptTree(query: OrgDeptTreeQuery): Promise<unknown> {
    return this.#get(
      '/data-source/dept-tree',
      query.status === undefined || query.status === '' ? {} : { status: query.status },
    )
  }

  /**
   * 批量回显。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async resolveNames(query: OrgResolveQuery): Promise<unknown> {
    return this.#get('/resolve-names', buildOrgResolveQuery(query.target, query.ids))
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
    // 端点：显式覆盖优先；否则按目录取址（**经寻址契约组装**，不自拼前缀）。解析为 null 即降级不发请求
    const resolved = this.#options.endpoint ?? orgSourceEndpoint()
    if (resolved === null) {
      if (!endpointWarningEmitted) {
        endpointWarningEmitted = true
        console.warn('[org-source] 组织数据源端点不可用（目录未就绪或未登记数据源类能力）：已跳过请求')
      }
      return undefined
    }
    const endpoint = resolved.replace(/\/+$/, '')
    const search = new URLSearchParams()
    appendOrgSearchParams(search, params)
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
 * 追加组织数据源查询参数（跳过空值：`undefined` / `null` / 空串 / `false`；布尔真写 `true`）。
 *
 * 抽为独立函数是为了让「空值过滤」这一分支可被直接用例覆盖（服务端参数口径与后端同源，
 * 空值必须**不出现**在查询串里，否则后端会按空串过滤而不是不过滤）。
 *
 * @param search 目标参数集（就地写入）。
 * @param params 参数映射。
 */
export function appendOrgSearchParams(search: URLSearchParams, params: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) {
      continue
    }
    search.set(key, value === true ? 'true' : String(value))
  }
}

/**
 * 组织数据源默认端点（**运行期取自平台目录快照**）。
 *
 * 按「业务域 `org` + 能力种类 `dataset`」解析提供方产品键与前端域段，经寻址契约组装为
 * `/api/{产品键}/v1/{域段}`——产品服务只经产品命名空间对外暴露，页面 / 插件**不得自拼** `/api/...`
 * 前缀（前端架构 §9 治理表）。
 *
 * @returns 端点前缀；目录未就绪 / 该域无数据源类能力 / 目标不唯一时返回 `null`（调用方进入降级）。
 */
export function orgSourceEndpoint(): string | null {
  const target = resolveCapabilityEndpoint(ORG_SOURCE_DOMAIN, ORG_SOURCE_CAPABILITY_KIND)
  return target.status === 'ok' ? target.endpoint : null
}

/**
 * 创建 HTTP 内建组织数据源。
 *
 * @param options 装载选项（`endpoint` 缺省＝按目录取址，见 `orgSourceEndpoint`）。
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
