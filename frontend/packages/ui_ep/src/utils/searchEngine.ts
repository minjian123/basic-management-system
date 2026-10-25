/**
 * 检索通道单一落点：HTTP 内建检索引擎（`fetch`）与检索引擎注册表默认实例。
 *
 * 可替换实现（纵向）继承核心插件基类 `BaseSearchEngine`，经 `searchEngineRegistry` 登记接入；
 * 未登记 / 未注入时搜索能力占位零请求。第三方 / 浏览器能力集中于此，件层不直用。
 */

import {
  BaseSearchEngine,
  SearchEngineProvider,
  SearchEngineRegistry,
  SEARCH_SUGGEST_LIMIT,
  type SearchEngineOptions,
  type SearchFileRequest,
  type SearchGlobalRequest,
  type SearchLogRequest,
} from '@bms/core'

/** 检索引擎注册表（默认实例；宿主可登记定制实现或覆盖内建键）。 */
export const searchEngineRegistry = new SearchEngineRegistry()

/**
 * 登记检索引擎实现。
 *
 * @param key 引擎键。
 * @param create 引擎工厂。
 */
export function registerSearchEngine(
  key: string,
  create: (options: SearchEngineOptions) => BaseSearchEngine | Promise<BaseSearchEngine>,
): void {
  searchEngineRegistry.register(new SearchEngineProvider(key, create))
}

/** 组装查询串（忽略 `undefined` / 空串）。 */
function toQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') {
      continue
    }
    if (Array.isArray(value)) {
      if (value.length > 0) {
        search.set(key, value.join(','))
      }
      continue
    }
    search.set(key, String(value))
  }
  return search.toString()
}

/** HTTP 内建检索引擎（`fetch` 单一落点）。 */
class HttpSearchEngine extends BaseSearchEngine {
  /** 实现名。 */
  override readonly pluginName: string = 'http'
  /** 装载选项。 */
  readonly #options: SearchEngineOptions

  /**
   * 构造 HTTP 内建检索引擎。
   *
   * @param options 装载选项。
   */
  constructor(options: SearchEngineOptions = {}) {
    super()
    this.#options = options
  }

  /** 端点前缀（缺省 `/api/v1`）。 */
  get endpoint(): string {
    return (this.#options.endpoint ?? '/api/v1').replace(/\/$/, '')
  }

  /** 请求头（函数形式每次解析）。 */
  get headers(): Record<string, string> {
    const source = this.#options.headers
    return typeof source === 'function' ? source() : (source ?? {})
  }

  /**
   * 发起一次检索请求。
   *
   * @param path 路径（如 `/search/global`）。
   * @param params 查询参数。
   * @returns 原始结果（能力不可用时返回 `undefined`，不抛错）。
   */
  async #request(path: string, params: Record<string, unknown>): Promise<unknown> {
    if (typeof fetch !== 'function') {
      return undefined
    }
    const query = toQuery(params)
    const url = `${this.endpoint}${path}${query === '' ? '' : `?${query}`}`
    const response = await fetch(url, { method: 'GET', headers: this.headers })
    if (!response.ok) {
      const error = new Error(`检索失败（${response.status}）`) as Error & { code?: number }
      error.code = response.status === 429 ? 10105 : 10101
      throw error
    }
    return response.json() as Promise<unknown>
  }

  /**
   * 即时建议（复用 `/search/global`，取各域首屏）。
   *
   * @param input 关键词与限定域。
   * @returns 原始结果。
   */
  override suggest(input: { keyword: string; types?: readonly string[] }): Promise<unknown> {
    return this.#request('/search/global', {
      q: input.keyword,
      types: input.types,
      page: 1,
      size: SEARCH_SUGGEST_LIMIT,
    })
  }

  /**
   * 全局检索。
   *
   * @param input 检索请求。
   * @returns 原始结果。
   */
  override searchGlobal(input: SearchGlobalRequest): Promise<unknown> {
    return this.#request('/search/global', {
      q: input.keyword,
      types: input.types,
      page: input.page,
      size: input.pageSize,
    })
  }

  /**
   * 审计日志检索。
   *
   * @param input 检索请求。
   * @returns 原始结果。
   */
  override searchLogs(input: SearchLogRequest): Promise<unknown> {
    return this.#request('/search/logs', {
      q: input.keyword,
      log_type: input.logType,
      start_time: input.start,
      end_time: input.end,
      page: input.page,
      size: input.pageSize,
    })
  }

  /**
   * 文件内容检索。
   *
   * @param input 检索请求。
   * @returns 原始结果。
   */
  override searchFiles(input: SearchFileRequest): Promise<unknown> {
    return this.#request('/search/files', {
      q: input.keyword,
      file_type: input.fileType,
      page: input.page,
      size: input.pageSize,
    })
  }
}

/**
 * 创建 HTTP 内建检索引擎。
 *
 * @param options 装载选项。
 * @returns 检索引擎实例。
 */
export function createHttpSearchEngine(options: SearchEngineOptions = {}): BaseSearchEngine {
  return new HttpSearchEngine(options)
}

registerSearchEngine('http', (options) => createHttpSearchEngine(options))
