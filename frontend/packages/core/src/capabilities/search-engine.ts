/**
 * 检索引擎插件基类与提供者注册表：检索引擎为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseSearchEngine`，经 `SearchEngineRegistry` 登记接入；
 * 未登记 / 未注入时搜索能力即占位（不发请求）。
 */

import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'

/** 全局检索请求。 */
export interface SearchGlobalRequest {
  /** 关键词。 */
  keyword: string
  /** 限定域（空表示全部可检索域）。 */
  types?: readonly string[]
  /** 页码（自 1）。 */
  page: number
  /** 页长。 */
  pageSize: number
}

/** 审计日志检索请求。 */
export interface SearchLogRequest {
  /** 关键词。 */
  keyword: string
  /** 日志类型（缺省不限定）。 */
  logType?: string
  /** 起点。 */
  start: string
  /** 终点。 */
  end: string
  /** 页码（自 1）。 */
  page: number
  /** 页长。 */
  pageSize: number
}

/** 文件内容检索请求。 */
export interface SearchFileRequest {
  /** 关键词。 */
  keyword: string
  /** 文件类型（缺省不限定）。 */
  fileType?: string
  /** 页码（自 1）。 */
  page: number
  /** 页长。 */
  pageSize: number
}

/** 检索适配器契约面（方法与 `BaseSearchEngine` 一致）。 */
export interface SearchEngineAdapter {
  /** 即时建议（未覆写返回 `undefined`，即不请求）。 */
  suggest?(input: { keyword: string; types?: readonly string[] }): Promise<unknown>
  /** 全局检索。 */
  searchGlobal?(input: SearchGlobalRequest): Promise<unknown>
  /** 审计日志检索。 */
  searchLogs?(input: SearchLogRequest): Promise<unknown>
  /** 文件内容检索。 */
  searchFiles?(input: SearchFileRequest): Promise<unknown>
}

/** 检索引擎装载选项。 */
export interface SearchEngineOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/** 检索引擎插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseSearchEngine extends BasePluggable implements SearchEngineAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'search-engine'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 即时建议。
   *
   * @param input 关键词与限定域。
   * @returns 原始结果（缺省 `undefined`）。
   */
  suggest(input: { keyword: string; types?: readonly string[] }): Promise<unknown> {
    void input
    return Promise.resolve(undefined)
  }

  /**
   * 全局检索。
   *
   * @param input 检索请求。
   * @returns 原始结果（缺省 `undefined`）。
   */
  searchGlobal(input: SearchGlobalRequest): Promise<unknown> {
    void input
    return Promise.resolve(undefined)
  }

  /**
   * 审计日志检索。
   *
   * @param input 检索请求。
   * @returns 原始结果（缺省 `undefined`）。
   */
  searchLogs(input: SearchLogRequest): Promise<unknown> {
    void input
    return Promise.resolve(undefined)
  }

  /**
   * 文件内容检索。
   *
   * @param input 检索请求。
   * @returns 原始结果（缺省 `undefined`）。
   */
  searchFiles(input: SearchFileRequest): Promise<unknown> {
    void input
    return Promise.resolve(undefined)
  }
}

/** 检索引擎注册项（工厂创建插件实例）。 */
export class SearchEngineProvider extends BaseProvider {
  /** 引擎键（如 `http`）。 */
  readonly key: string
  /** 引擎工厂。 */
  readonly create: (options: SearchEngineOptions) => BaseSearchEngine | Promise<BaseSearchEngine>

  /**
   * 构造检索引擎注册项。
   *
   * @param key 引擎键。
   * @param create 引擎工厂。
   */
  constructor(key: string, create: (options: SearchEngineOptions) => BaseSearchEngine | Promise<BaseSearchEngine>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 检索引擎注册表（统一注册表基座；同键唯一性拒重）。 */
export class SearchEngineRegistry extends BaseProviderRegistry<SearchEngineProvider> {
  /** 插件键。 */
  readonly pluginKey = 'search-engine-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: SearchEngineProvider): string {
    return provider.key
  }
}
