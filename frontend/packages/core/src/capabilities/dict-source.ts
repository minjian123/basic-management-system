/**
 * 字典数据源插件基类与提供者注册表：字典数据源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseDictSource`，经 `DictSourceRegistry` 登记接入；
 * 未登记 / 未注入时字典能力即占位（不发请求）。
 *
 * 方法对应后端字典出口（普通取数与高级查询同一数据源）：
 * `GET /api/v1/dicts/{type}`、`POST /api/v1/dicts/batch`、`GET /api/v1/dicts/{type}/attrs`、
 * `GET /api/v1/dicts/query-providers`、`POST /api/v1/dicts/{type}/advanced-query`、
 * `/api/v1/query-schemes`（清单 / 默认 / 保存 / 删除）。
 */

import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'
import type {
  DictConditionGroup,
  DictQueryProvider,
  DictQueryScheme,
  DictTarget,
} from '../domain/dict'

/** 单类型取数入参（与后端 `DictQuery` 同形）。 */
export interface DictSourceTypeQuery {
  /** 字典类型码。 */
  dictType: string
  /** 客户端本地版本号（一致时后端返回 `items=null`）。 */
  version?: number
  /** 关键字（label / value / code）。 */
  keyword?: string
  /** 级联父值（空串 = 顶层）。 */
  parentId?: string
  /** 指定 value 子集（批量翻译）。 */
  values?: readonly string[]
  /** 返回条数上限（探针传 2001）。 */
  limit?: number
}

/** 批量取数入参。 */
export interface DictSourceBatchQuery {
  /** 字典类型码序列。 */
  types: readonly string[]
  /** 客户端本地版本号。 */
  version?: number
  /** 语言。 */
  locale?: string
}

/** 属性 schema 入参。 */
export interface DictSourceAttrsQuery {
  /** 字典类型码。 */
  dictType: string
  /** 语言。 */
  locale?: string
}

/** 提供者清单入参。 */
export interface DictSourceProvidersQuery {
  /** 按字典类型过滤（可选）。 */
  dictType?: string
}

/** 高级查询入参。 */
export interface DictSourceAdvQuery {
  /** 字典类型码。 */
  dictType: string
  /** 目标（取项 / 业务筛选）。 */
  target: DictTarget
  /** 条件组。 */
  conditions?: DictConditionGroup
  /** 查询提供者键。 */
  provider?: string
  /** 提供者参数。 */
  params?: Record<string, unknown>
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  size?: number
}

/** 查询方案入参。 */
export interface DictSourceSchemeQuery {
  /** 目标。 */
  target: DictTarget
  /** 表单标识（列表筛选维度；可选）。 */
  fieldKey?: string
  /** 方案 ID（详情 / 删除）。 */
  schemeId?: number
  /** 方案（保存）。 */
  scheme?: DictQueryScheme
}

/** 字典数据源契约面（方法与 `BaseDictSource` 一致；未覆写的方法返回 `undefined`，即不请求）。 */
export interface DictSourceAdapter {
  /** 单类型取数。 */
  getType?(query: DictSourceTypeQuery): Promise<unknown>
  /** 批量取数（多类型合并）。 */
  batch?(query: DictSourceBatchQuery): Promise<unknown>
  /** 属性 schema（高级查询条件字段）。 */
  loadAttrs?(query: DictSourceAttrsQuery): Promise<unknown>
  /** 查询提供者清单。 */
  loadProviders?(query: DictSourceProvidersQuery): Promise<unknown>
  /** 高级查询（取项 / 业务筛选）。 */
  advancedQuery?(query: DictSourceAdvQuery): Promise<unknown>
  /** 查询方案清单。 */
  listSchemes?(query: DictSourceSchemeQuery): Promise<unknown>
  /** 默认方案解析。 */
  resolveDefaultScheme?(query: DictSourceSchemeQuery): Promise<unknown>
  /** 保存方案。 */
  saveScheme?(query: DictSourceSchemeQuery): Promise<unknown>
  /** 删除方案。 */
  deleteScheme?(query: DictSourceSchemeQuery): Promise<unknown>
}

/** 数据源装载选项。 */
export interface DictSourceOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/** 字典数据源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseDictSource extends BasePluggable implements DictSourceAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'dict-source'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 单类型取数。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  getType(query: DictSourceTypeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 批量取数。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  batch(query: DictSourceBatchQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 属性 schema。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  loadAttrs(query: DictSourceAttrsQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 查询提供者清单。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  loadProviders(query: DictSourceProvidersQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 高级查询。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  advancedQuery(query: DictSourceAdvQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 查询方案清单。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  listSchemes(query: DictSourceSchemeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 默认方案解析。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  resolveDefaultScheme(query: DictSourceSchemeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 保存方案。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  saveScheme(query: DictSourceSchemeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 删除方案。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  deleteScheme(query: DictSourceSchemeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }
}

/** 数据源注册项（工厂创建插件实例）。 */
export class DictSourceProvider extends BaseProvider {
  /** 数据源键（如 `http`）。 */
  readonly key: string
  /** 数据源工厂。 */
  readonly create: (options: DictSourceOptions) => BaseDictSource | Promise<BaseDictSource>

  /**
   * 构造数据源注册项。
   *
   * @param key 数据源键。
   * @param create 数据源工厂。
   */
  constructor(key: string, create: (options: DictSourceOptions) => BaseDictSource | Promise<BaseDictSource>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class DictSourceRegistry extends BaseProviderRegistry<DictSourceProvider> {
  /** 插件键。 */
  readonly pluginKey = 'dict-source-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: DictSourceProvider): string {
    return provider.key
  }
}

/** 查询提供者清单归一（脏项剔除；供高级查询投影使用）。 */
export type DictQueryProviderList = DictQueryProvider[]
