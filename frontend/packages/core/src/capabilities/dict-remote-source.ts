/**
 * 字典数据源插件基类与提供者注册表：字典数据源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseDictRemoteSource`，经 `DictRemoteSourceRegistry` 登记接入；
 * 未登记 / 未注入时远程字典选择能力即占位（不发请求）。
 *
 * 四方法对应**字典数据出口**（查询与批量回显分列两个出口）——字典数据归**主数据产品**，
 * 出口经**产品命名空间**暴露：`/api/{产品键}/v1/{域段}/data-source/{users,posts,dept-tree}` 与
 * `/api/{产品键}/v1/{域段}/resolve-names`（前端默认端点按目录快照取址，见 `@bms/ui_ep` 的 `dictRemoteSourceEndpoint`）；
 * 契约（数据契约与插件基类）原在基座主数据查询能力，已随阶段二 `11_02` 迁出基座。
 */

import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'
import type { DictDataKind, DictDataStatus } from '../domain/dict-data'

/** 用户查询入参（与后端 `users(...)` 同形；数据范围与脱敏由实现侧强制）。 */
export interface DictUserQuery {
  /** 关键词（用户名 / 昵称 / 手机号）。 */
  keyword?: string
  /** 部门过滤。 */
  deptId?: string
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 状态过滤。 */
  status?: DictDataStatus | ''
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 岗位查询入参（与后端 `posts(...)` 同形）。 */
export interface DictPostQuery {
  /** 关键词（名称 / 编码）。 */
  keyword?: string
  /** 部门过滤。 */
  deptId?: string
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 状态过滤。 */
  status?: DictDataStatus | ''
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 部门树查询入参（一次性返回、不分页）。 */
export interface DictDeptTreeQuery {
  /** 状态过滤。 */
  status?: DictDataStatus | ''
}

/** 批量回显入参。 */
export interface DictResolveQuery {
  /** 对象类型。 */
  target: DictDataKind
  /** 标识列表（一次批量，避免 N+1）。 */
  ids: readonly string[]
}

/** 字典数据源契约面（方法与 `BaseDictRemoteSource` 一致）。 */
export interface DictRemoteSourceAdapter {
  /** 用户查询。 */
  searchUsers?(query: DictUserQuery): Promise<unknown>
  /** 岗位查询。 */
  searchPosts?(query: DictPostQuery): Promise<unknown>
  /** 部门树（一次性返回；节点含 `code` 部门编码）。 */
  loadDeptTree?(query: DictDeptTreeQuery): Promise<unknown>
  /** 按 id 批量回显名称。 */
  resolveNames?(query: DictResolveQuery): Promise<unknown>
}

/** 数据源装载选项。 */
export interface DictRemoteSourceOptions {
  /** 端点前缀（缺省＝按目录快照取址，见 `@bms/ui_ep` 的 `dictRemoteSourceEndpoint`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/** 字典数据源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseDictRemoteSource extends BasePluggable implements DictRemoteSourceAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'dict-remote-source'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 用户查询。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  searchUsers(query: DictUserQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 岗位查询。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  searchPosts(query: DictPostQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 部门树查询。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  loadDeptTree(query: DictDeptTreeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 批量回显。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  resolveNames(query: DictResolveQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }
}

/** 字典数据源注册项（工厂创建插件实例）。 */
export class DictRemoteSourceProvider extends BaseProvider {
  /** 数据源键（如 `http`）。 */
  readonly key: string
  /** 数据源工厂。 */
  readonly create: (options: DictRemoteSourceOptions) => BaseDictRemoteSource | Promise<BaseDictRemoteSource>

  /**
   * 构造数据源注册项。
   *
   * @param key 数据源键。
   * @param create 数据源工厂。
   */
  constructor(key: string, create: (options: DictRemoteSourceOptions) => BaseDictRemoteSource | Promise<BaseDictRemoteSource>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 字典数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class DictRemoteSourceRegistry extends BaseProviderRegistry<DictRemoteSourceProvider> {
  /** 插件键。 */
  readonly pluginKey = 'dict-remote-source-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: DictRemoteSourceProvider): string {
    return provider.key
  }
}
