/**
 * 组织数据源插件基类与提供者注册表：组织数据源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseOrgSource`，经 `OrgSourceRegistry` 登记接入；
 * 未登记 / 未注入时组织选择能力即占位（不发请求）。
 *
 * 四方法对应后端组织主数据出口（查询与批量回显分列两个出口）：
 * `/api/v1/org/users`、`/api/v1/org/posts`、`/api/v1/org/dept-tree`、`/api/v1/org/resolve-names`。
 */

import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'
import type { OrgKind, OrgStatus } from '../domain/org'

/** 用户查询入参（与后端 `users(...)` 同形；数据范围与脱敏由实现侧强制）。 */
export interface OrgUserQuery {
  /** 关键词（用户名 / 昵称 / 手机号）。 */
  keyword?: string
  /** 部门过滤。 */
  deptId?: string
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 状态过滤。 */
  status?: OrgStatus | ''
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 岗位查询入参（与后端 `posts(...)` 同形）。 */
export interface OrgPostQuery {
  /** 关键词（名称 / 编码）。 */
  keyword?: string
  /** 部门过滤。 */
  deptId?: string
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 状态过滤。 */
  status?: OrgStatus | ''
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 部门树查询入参（一次性返回、不分页）。 */
export interface OrgDeptTreeQuery {
  /** 状态过滤。 */
  status?: OrgStatus | ''
}

/** 批量回显入参。 */
export interface OrgResolveQuery {
  /** 对象类型。 */
  target: OrgKind
  /** 标识列表（一次批量，避免 N+1）。 */
  ids: readonly string[]
}

/** 组织数据源契约面（方法与 `BaseOrgSource` 一致）。 */
export interface OrgSourceAdapter {
  /** 用户查询。 */
  searchUsers?(query: OrgUserQuery): Promise<unknown>
  /** 岗位查询。 */
  searchPosts?(query: OrgPostQuery): Promise<unknown>
  /** 部门树（一次性返回）。 */
  loadDeptTree?(query: OrgDeptTreeQuery): Promise<unknown>
  /** 按 id 批量回显名称。 */
  resolveNames?(query: OrgResolveQuery): Promise<unknown>
}

/** 数据源装载选项。 */
export interface OrgSourceOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/** 组织数据源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseOrgSource extends BasePluggable implements OrgSourceAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'org-source'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 用户查询。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  searchUsers(query: OrgUserQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 岗位查询。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  searchPosts(query: OrgPostQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 部门树查询。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  loadDeptTree(query: OrgDeptTreeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 批量回显。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  resolveNames(query: OrgResolveQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }
}

/** 组织数据源注册项（工厂创建插件实例）。 */
export class OrgSourceProvider extends BaseProvider {
  /** 数据源键（如 `http`）。 */
  readonly key: string
  /** 数据源工厂。 */
  readonly create: (options: OrgSourceOptions) => BaseOrgSource | Promise<BaseOrgSource>

  /**
   * 构造数据源注册项。
   *
   * @param key 数据源键。
   * @param create 数据源工厂。
   */
  constructor(key: string, create: (options: OrgSourceOptions) => BaseOrgSource | Promise<BaseOrgSource>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 组织数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class OrgSourceRegistry extends BaseProviderRegistry<OrgSourceProvider> {
  /** 插件键。 */
  readonly pluginKey = 'org-source-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: OrgSourceProvider): string {
    return provider.key
  }
}
