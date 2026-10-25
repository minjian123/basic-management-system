/**
 * 通用页面路由能力基类（能力键 `page-route`）：按 `form_key` 解析页面 / 表单
 * （表单标识 → 页面：路由 + 视图 + 表单框架配置 + 数据源 + 联动键）。
 *
 * - **声明**：宿主登记「表单标识 → 页面」声明（路由 / 列表与详情组件 / 标题 / meta / 可选显式数据源）；
 * - **清单**：经营注入适配器加载数据源（`GET /api/v1/data-sources`）与表单标识（`GET /api/v1/form-keys`）清单，
 *   解析 `form_key → data_source_key`（多对一）；
 * - **联动**：派生列表偏好键 `list.{form_key}` 与查询方案表单标识 `field_key = form_key`；
 * - **占位**：未注入适配器 / 未就绪即占位零请求（`requestCount` 恒 0），`resolve()` 返回 `undefined`；
 *   路由挂载动作由宿主注入（核心不依赖渲染框架与路由库）。
 */

import { BasePlaceholderState } from './placeholder-state'
import { buildListPrefKey } from '../domain/list-preference'
import {
  normalizeDataSourceRecords,
  normalizeFormKeyRecords,
  normalizeFormPageDeclaration,
  resolvePageRoute,
  type DataSourceRecord,
  type FormKeyRecord,
  type FormPageDeclaration,
  type PageRouteResolution,
} from '../domain/page-route'

/** 清单装载适配器（宿主注入；未注入即占位零请求）。 */
export interface PageRouteAdapter {
  /** 加载数据源登记清单（返回原始响应体）。 */
  loadDataSources?(): Promise<unknown>
  /** 加载表单标识清单（返回原始响应体）。 */
  loadFormKeys?(): Promise<unknown>
}

/** 通用页面路由能力基类（抽象）。 */
export abstract class BasePageRoute extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'page_route'
  /** 依赖能力键（占位状态）。 */
  override readonly depends = ['placeholder_state']
  /** 清单装载适配器（宿主注入；缺省占位零请求）。 */
  adapter: PageRouteAdapter | undefined
  /** 数据源登记清单（保序）。 */
  dataSources: DataSourceRecord[] = []
  /** 表单标识登记清单（保序）。 */
  formKeys: FormKeyRecord[] = []
  /** 是否已成功装载清单。 */
  loaded = false
  /** 装载失败原因（成功为 `undefined`）。 */
  error: string | undefined

  /** 表单页声明（表单标识 → 声明；插入序）。 */
  readonly #declarations = new Map<string, FormPageDeclaration>()
  /** 进行中的装载（并发去重；模块内态）。 */
  #inflight: Promise<void> | undefined

  /**
   * 登记表单页声明（同键拒重；非法声明丢弃）。
   *
   * @param declaration 表单页声明。
   * @returns 是否登记成功。
   */
  declare(declaration: FormPageDeclaration): boolean {
    const normalized = normalizeFormPageDeclaration(declaration)
    if (normalized === undefined || this.#declarations.has(normalized.formKey)) {
      return false
    }
    this.#declarations.set(normalized.formKey, normalized)
    this.#notify()
    return true
  }

  /**
   * 批量登记表单页声明（跳过非法 / 重复）。
   *
   * @param declarations 声明清单。
   * @returns 成功登记数量。
   */
  declareAll(declarations: readonly FormPageDeclaration[]): number {
    let count = 0
    for (const declaration of declarations) {
      if (this.declare(declaration)) {
        count += 1
      }
    }
    return count
  }

  /** 已登记声明清单（插入序）。 */
  declarations(): FormPageDeclaration[] {
    return [...this.#declarations.values()]
  }

  /**
   * 取表单页声明。
   *
   * @param formKey 表单标识。
   * @returns 声明；未登记返回 `undefined`。
   */
  declarationOf(formKey: string): FormPageDeclaration | undefined {
    return this.#declarations.get(formKey)
  }

  /**
   * 是否字典记录页（表单标识命中且数据形态为字典）。
   *
   * 字典记录页据此套用《布局设计 · 字典页》骨架；清单未装载 / 未命中的表单标识返回 `false`（占位零请求语义不变）。
   *
   * @param formKey 表单标识。
   * @returns 是否字典。
   */
  isDictPage(formKey: string): boolean {
    return this.formKeys.find((entry) => entry.formKey === formKey)?.isDict === true
  }

  /**
   * 是否字典数据源（数据源标识命中且数据形态为字典）。
   *
   * @param dataSourceKey 数据源标识。
   * @returns 是否字典；清单未装载 / 未命中返回 `false`。
   */
  isDictDataSource(dataSourceKey: string): boolean {
    return this.dataSources.find((entry) => entry.dataSourceKey === dataSourceKey)?.isDict === true
  }

  /**
   * 解析数据源标识（`form_key → data_source_key`）。
   *
   * @param formKey 表单标识。
   * @returns 数据源标识；未解析返回 `undefined`。
   */
  dataSourceKeyOf(formKey: string): string | undefined {
    const declaration = this.#declarations.get(formKey)
    if (declaration === undefined) {
      return undefined
    }
    const resolution = resolvePageRoute(declaration, this.formKeys, this.dataSources)
    return resolution?.dataSourceKey
  }

  /**
   * 按表单标识解析页面（路由 + 视图 + 表单框架配置 + 数据源 + 联动键）。
   *
   * @param formKey 表单标识。
   * @returns 解析结果；未声明 / 数据源未登记 / 未就绪返回 `undefined`。
   */
  resolve(formKey: string): PageRouteResolution | undefined {
    const declaration = this.#declarations.get(formKey)
    if (declaration === undefined) {
      return undefined
    }
    return resolvePageRoute(declaration, this.formKeys, this.dataSources)
  }

  /**
   * 列表偏好键（`list.{form_key}`）。
   *
   * @param formKey 表单标识。
   * @returns 偏好键。
   */
  listPreferenceKeyOf(formKey: string): string {
    return buildListPrefKey(formKey)
  }

  /**
   * 查询方案表单标识（`field_key = form_key`）。
   *
   * @param formKey 表单标识。
   * @returns 表单标识（原值，供约定引用）。
   */
  schemeFieldKeyOf(formKey: string): string {
    return formKey
  }

  /**
   * 装载清单（幂等；并发去重；未注入适配器即占位零请求）。
   *
   * 失败置降级态并保留错误信息（不抛断）。
   */
  async load(): Promise<void> {
    if (this.loaded) {
      return
    }
    if (this.#inflight !== undefined) {
      return this.#inflight
    }
    const adapter = this.adapter
    if (adapter === undefined) {
      this.setReady(false)
      return
    }
    this.setReady(true)
    this.#inflight = this.#fetch(adapter)
    try {
      await this.#inflight
    } finally {
      this.#inflight = undefined
    }
  }

  /** 清空清单（登出 / 会话失效；声明保留）。 */
  reset(): void {
    this.dataSources = []
    this.formKeys = []
    this.loaded = false
    this.error = undefined
    this.setReady(false)
    this.#notify()
  }

  /**
   * 拉取数据源与表单标识清单。
   *
   * @param adapter 清单装载适配器。
   */
  async #fetch(adapter: PageRouteAdapter): Promise<void> {
    try {
      const [dataSourcesRaw, formKeysRaw] = await Promise.all([
        adapter.loadDataSources === undefined ? Promise.resolve(undefined) : adapter.loadDataSources(),
        adapter.loadFormKeys === undefined ? Promise.resolve(undefined) : adapter.loadFormKeys(),
      ])
      this.markLoaded()
      this.dataSources = normalizeDataSourceRecords(dataSourcesRaw)
      this.formKeys = normalizeFormKeyRecords(formKeysRaw)
      this.loaded = true
      this.error = undefined
    } catch (error: unknown) {
      this.error = error instanceof Error ? error.message : String(error)
    }
    this.#notify()
  }

  /** 生命周期通知（未释放才通知）。 */
  #notify(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
