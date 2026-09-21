/**
 * 字典高级查询编排能力基类 `BaseDictQuery`：属性 schema / 提供者清单 / 条件组 /
 * 执行（取项条件引擎 / 业务筛选提供者）/ 查询方案（列表 / 默认 / 应用 / 保存 / 删除）。
 *
 * 继承链：`BaseComponent → BasePlaceholderState → BaseDictQuery`（能力基类）；
 * 元数据与执行经注入式 `DictSourceAdapter`（未注入即占位零请求）；条件组构建与抽屉渲染归件层。
 */

import { BasePlaceholderState } from './placeholder-state'
import {
  clampDictPage,
  clampDictPageSize,
  dictAttrFieldOptions,
  dictFixedFieldOptions,
  normalizeConditionGroup,
  normalizeDictItems,
  normalizeDictQueryScheme,
  validateConditionGroup,
  type DictAttrFieldOption,
  type DictAttrSchema,
  type DictConditionGroup,
  type DictItem,
  type DictQueryProvider,
  type DictQueryScheme,
  type DictTarget,
} from '../domain/dict'
import type { DictSourceAdapter } from './dict-source'

/** 属性 schema 归一（脏项剔除）。 */
function normalizeAttrs(raw: unknown): DictAttrSchema[] {
  if (!Array.isArray(raw)) {
    return []
  }
  const attrs: DictAttrSchema[] = []
  for (const entry of raw) {
    if (entry === null || typeof entry !== 'object') {
      continue
    }
    const record = entry as Record<string, unknown>
    const key = record.attrKey ?? record.attr_key
    if (typeof key !== 'string' || key === '') {
      continue
    }
    const dataTypeRaw = record.dataType ?? record.data_type
    const dataType = (
      dataTypeRaw === 'number' || dataTypeRaw === 'date' || dataTypeRaw === 'enum' || dataTypeRaw === 'bool'
        ? dataTypeRaw
        : 'text'
    ) as DictAttrSchema['dataType']
    const operatorsRaw = record.operators
    const operators = Array.isArray(operatorsRaw)
      ? operatorsRaw.filter((item): item is DictAttrSchema['operators'][number] => typeof item === 'string')
      : []
    const optionsRaw = record.options
    const options = Array.isArray(optionsRaw)
      ? optionsRaw
          .filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object')
          .map((item) => ({ label: String(item.label ?? ''), value: String(item.value ?? '') }))
      : undefined
    const sortRaw = record.sort
    attrs.push({
      attrKey: key,
      name: typeof record.name === 'string' ? record.name : key,
      dataType,
      operators,
      widget: typeof record.widget === 'string' ? record.widget : undefined,
      options,
      sort: typeof sortRaw === 'number' ? sortRaw : 0,
      scope: typeof record.scope === 'string' ? record.scope : 'platform',
    })
  }
  return attrs
}

/** 查询提供者归一（脏项剔除）。 */
function normalizeProviders(raw: unknown): DictQueryProvider[] {
  if (!Array.isArray(raw)) {
    return []
  }
  const providers: DictQueryProvider[] = []
  for (const entry of raw) {
    if (entry === null || typeof entry !== 'object') {
      continue
    }
    const record = entry as Record<string, unknown>
    const key = record.key
    if (typeof key !== 'string' || key === '') {
      continue
    }
    const target = record.target === 'items' ? 'items' : 'business'
    const dictTypesRaw = record.dictTypes ?? record.dict_types
    const paramSchemaRaw = record.paramSchema ?? record.param_schema
    providers.push({
      key,
      name: typeof record.name === 'string' ? record.name : key,
      target,
      dictTypes: Array.isArray(dictTypesRaw) ? dictTypesRaw.map((item) => String(item)) : [],
      paramSchema:
        paramSchemaRaw !== null && typeof paramSchemaRaw === 'object' && !Array.isArray(paramSchemaRaw)
          ? (paramSchemaRaw as Record<string, unknown>)
          : {},
    })
  }
  return providers
}

/** 高级查询结果归一。 */
function normalizeAdvResult(raw: unknown): { items: DictItem[]; rows: Record<string, unknown>[]; total: number } {
  if (raw === null || typeof raw !== 'object') {
    return { items: [], rows: [], total: 0 }
  }
  const record = raw as Record<string, unknown>
  const rowsRaw = record.rows
  const rows = Array.isArray(rowsRaw)
    ? rowsRaw
        .filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object')
        .map((item) => ({ ...item }))
    : []
  const totalRaw = record.total
  return {
    items: normalizeDictItems(record.items),
    rows,
    total: typeof totalRaw === 'number' && Number.isFinite(totalRaw) ? totalRaw : 0,
  }
}

/** 字典高级查询编排能力基类（抽象）。 */
export abstract class BaseDictQuery extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'dict-query'
  /** 依赖登记。 */
  override readonly depends = ['placeholder-state', 'dict-store']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 字典类型码。 */
  dictType = ''
  /** 目标（取项 / 业务筛选）。 */
  target: DictTarget = 'items'
  /** 属性 schema（元数据）。 */
  readonly attrs: DictAttrSchema[] = []
  /** 查询提供者清单（元数据）。 */
  readonly providers: DictQueryProvider[] = []
  /** 条件组。 */
  conditions: DictConditionGroup = { logic: 'AND', children: [] }
  /** 查询提供者键。 */
  providerKey = ''
  /** 提供者参数。 */
  providerParams: Record<string, unknown> = {}
  /** 查询方案清单。 */
  readonly schemes: DictQueryScheme[] = []
  /** 取项结果（`target=items`）。 */
  readonly results: DictItem[] = []
  /** 业务筛选结果（`target=business`）。 */
  readonly rows: Record<string, unknown>[] = []
  /** 命中总数。 */
  total = 0
  /** 页码（自 1）。 */
  page = 1
  /** 页长。 */
  pageSize = 20
  /** 执行态。 */
  loading = false
  /** 错误码。 */
  errorCode: number | undefined
  /** 错误文案。 */
  errorMessage = ''
  /** 字典数据源（注入式；未注入即占位零请求）。 */
  source: DictSourceAdapter | undefined

  /** 执行请求序号（防旧响应覆盖）。 */
  #seq = 0

  /** 是否错误态。 */
  get error(): boolean {
    return this.errorCode !== undefined
  }

  /** 是否空态。 */
  get empty(): boolean {
    return !this.loading && this.errorCode === undefined && this.results.length === 0 && this.rows.length === 0
  }

  /** 元数据是否已加载。 */
  get metaLoaded(): boolean {
    return this.attrs.length > 0 || this.providers.length > 0
  }

  /** 条件构建件字段项（固定字段 + 属性）。 */
  get fieldOptions(): DictAttrFieldOption[] {
    return [...dictFixedFieldOptions(), ...dictAttrFieldOptions(this.attrs)]
  }

  /**
   * 注入 / 移除数据源（移除即回落占位零请求）。
   *
   * @param source 数据源适配器；`undefined` 表示移除。
   */
  setSource(source: DictSourceAdapter | undefined): void {
    this.source = source
    this.emitUpdate()
  }

  /**
   * 切换字典类型（清空元数据 / 条件 / 结果）。
   *
   * @param dictType 字典类型码。
   */
  setDictType(dictType: string): void {
    this.dictType = dictType.trim()
    this.attrs.splice(0, this.attrs.length)
    this.providers.splice(0, this.providers.length)
    this.reset()
  }

  /**
   * 切换目标（清空条件 / 提供者 / 结果）。
   *
   * @param target 目标。
   */
  setTarget(target: DictTarget): void {
    if (this.target === target) {
      return
    }
    this.target = target
    this.reset()
  }

  /**
   * 设置条件组（结构归一；非法忽略）。
   *
   * @param group 条件组。
   */
  setConditions(group: DictConditionGroup): void {
    const normalized = normalizeConditionGroup(group)
    if (normalized === undefined) {
      this.errorMessage = '条件组结构非法'
      this.emitUpdate()
      return
    }
    this.conditions = normalized
    this.emitUpdate()
  }

  /**
   * 设置查询提供者与参数。
   *
   * @param key 提供者键。
   * @param params 参数。
   */
  setProvider(key: string, params?: Record<string, unknown>): void {
    this.providerKey = key
    this.providerParams = params === undefined ? {} : { ...params }
    this.emitUpdate()
  }

  /**
   * 设置页码（夹取）。
   *
   * @param page 页码。
   */
  setPage(page: number): void {
    this.page = clampDictPage(page)
    this.emitUpdate()
  }

  /**
   * 设置页长（夹取 ≤ 100）。
   *
   * @param size 页长。
   */
  setPageSize(size: number): void {
    this.pageSize = clampDictPageSize(size)
    this.emitUpdate()
  }

  /**
   * 加载元数据（属性 schema + 提供者清单并行；单失败不整体报错）。
   *
   * @returns 无。
   */
  async loadMeta(): Promise<void> {
    if (!this.ready || this.dictType === '') {
      return
    }
    const adapter = this.source
    if (adapter === undefined) {
      return
    }
    const attrsLoader = adapter.loadAttrs
    const providersLoader = adapter.loadProviders
    if (attrsLoader === undefined && providersLoader === undefined) {
      return
    }
    this.markLoaded()
    this.loading = true
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    const [attrsResult, providersResult] = await Promise.all([
      attrsLoader === undefined ? Promise.resolve(undefined) : attrsLoader.call(adapter, { dictType: this.dictType }),
      providersLoader === undefined
        ? Promise.resolve(undefined)
        : providersLoader.call(adapter, { dictType: this.dictType }),
    ])
    this.attrs.splice(0, this.attrs.length, ...normalizeAttrs(attrsResult))
    this.providers.splice(0, this.providers.length, ...normalizeProviders(providersResult))
    this.loading = false
    this.emitUpdate()
  }

  /**
   * 执行高级查询（取项条件引擎 / 业务筛选提供者）。
   *
   * @returns 无。
   */
  async run(): Promise<void> {
    if (!this.ready || this.dictType === '') {
      return
    }
    const adapter = this.source
    const loader = adapter?.advancedQuery
    if (adapter === undefined || loader === undefined) {
      return
    }
    if (this.target === 'items') {
      const reason = validateConditionGroup(this.conditions, this.fieldOptions)
      if (reason !== undefined) {
        this.errorMessage = reason
        this.errorCode = undefined
        this.emitUpdate()
        return
      }
    }
    const token = (this.#seq += 1)
    this.markLoaded()
    this.loading = true
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw = await loader.call(adapter, {
        dictType: this.dictType,
        target: this.target,
        conditions: this.conditions,
        provider: this.providerKey === '' ? undefined : this.providerKey,
        params: this.providerParams,
        page: this.page,
        size: this.pageSize,
      })
      if (token !== this.#seq) {
        return
      }
      const result = normalizeAdvResult(raw)
      this.results.splice(0, this.results.length, ...result.items)
      this.rows.splice(0, this.rows.length, ...result.rows)
      this.total = result.total
      this.loading = false
      this.emitUpdate()
    } catch (error) {
      if (token !== this.#seq) {
        return
      }
      this.loading = false
      this.errorCode = readErrorCode(error)
      this.errorMessage = this.errorCode === undefined ? '查询执行失败' : `查询执行失败（${this.errorCode}）`
      this.reportError(error, { scope: 'BaseDictQuery.run' })
      this.emitUpdate()
    }
  }

  /** 重置条件 / 提供者 / 结果。 */
  reset(): void {
    this.conditions = { logic: 'AND', children: [] }
    this.providerKey = ''
    this.providerParams = {}
    this.results.splice(0, this.results.length)
    this.rows.splice(0, this.rows.length)
    this.total = 0
    this.page = 1
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
  }

  /**
   * 加载查询方案清单。
   *
   * @returns 无。
   */
  async loadSchemes(): Promise<void> {
    const adapter = this.source
    const loader = adapter?.listSchemes
    if (!this.ready || adapter === undefined || loader === undefined) {
      return
    }
    this.markLoaded()
    try {
      const raw = await loader.call(adapter, { target: this.target })
      const list = Array.isArray(raw) ? raw : []
      const schemes: DictQueryScheme[] = []
      for (const entry of list) {
        const scheme = normalizeDictQueryScheme(entry)
        if (scheme !== undefined) {
          schemes.push(scheme)
        }
      }
      this.schemes.splice(0, this.schemes.length, ...schemes)
      this.emitUpdate()
    } catch (error) {
      this.reportError(error, { scope: 'BaseDictQuery.loadSchemes' })
    }
  }

  /**
   * 解析默认方案（三级优先级）。
   *
   * @returns 无。
   */
  async resolveDefaultScheme(): Promise<void> {
    const adapter = this.source
    const loader = adapter?.resolveDefaultScheme
    if (!this.ready || adapter === undefined || loader === undefined) {
      return
    }
    this.markLoaded()
    try {
      const raw = await loader.call(adapter, { target: this.target })
      const scheme = normalizeDictQueryScheme(raw)
      if (scheme !== undefined) {
        this.applyScheme(scheme)
      }
    } catch (error) {
      this.reportError(error, { scope: 'BaseDictQuery.resolveDefaultScheme' })
    }
  }

  /**
   * 应用方案（载入条件 / 提供者 / 参数）。
   *
   * @param scheme 方案。
   */
  applyScheme(scheme: DictQueryScheme): void {
    if (scheme.conditions !== undefined) {
      this.conditions = scheme.conditions
    }
    this.providerKey = scheme.providerKey ?? ''
    this.providerParams = scheme.params === undefined ? {} : { ...scheme.params }
    this.emitUpdate()
  }

  /**
   * 保存方案（个人方案缺省 `scope=user`）。
   *
   * @param name 方案名。
   * @param scope 作用域（缺省个人）。
   * @param shared 是否共享。
   * @returns 无。
   */
  async saveScheme(name: string, scope?: DictQueryScheme['scope'], shared = false): Promise<void> {
    const adapter = this.source
    const loader = adapter?.saveScheme
    if (!this.ready || adapter === undefined || loader === undefined) {
      return
    }
    const scheme: DictQueryScheme = {
      name,
      scope: scope ?? 'user',
      target: this.target,
      dictType: this.dictType,
      providerKey: this.providerKey === '' ? undefined : this.providerKey,
      conditions: this.conditions,
      params: { ...this.providerParams },
      isDefault: false,
      shared,
    }
    this.markLoaded()
    try {
      await loader.call(adapter, { target: this.target, scheme })
      await this.loadSchemes()
    } catch (error) {
      this.reportError(error, { scope: 'BaseDictQuery.saveScheme' })
    }
  }

  /**
   * 删除方案。
   *
   * @param schemeId 方案 ID。
   * @returns 无。
   */
  async deleteScheme(schemeId: number): Promise<void> {
    const adapter = this.source
    const loader = adapter?.deleteScheme
    if (!this.ready || adapter === undefined || loader === undefined) {
      return
    }
    this.markLoaded()
    try {
      await loader.call(adapter, { target: this.target, schemeId })
      await this.loadSchemes()
    } catch (error) {
      this.reportError(error, { scope: 'BaseDictQuery.deleteScheme' })
    }
  }

  /**
   * 业务筛选参数（宿主消费）。
   *
   * @returns 筛选参数。
   */
  toBusinessFilter(): Record<string, unknown> {
    return {
      target: 'business',
      dict_type: this.dictType,
      provider: this.providerKey,
      params: { ...this.providerParams },
      conditions: this.conditions,
    }
  }

  /** 取项选中值（宿主回填字段）。 */
  selectedValues(): string[] {
    return this.results.map((item) => item.value)
  }

  /** 失效（清结果；条件保留）。 */
  invalidate(): void {
    this.results.splice(0, this.results.length)
    this.rows.splice(0, this.rows.length)
    this.total = 0
    this.emitUpdate()
  }

  /** 广播更新（已释放则忽略）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}

/**
 * 读取错误码（兼容 `code` / `errorCode`）。
 *
 * @param error 原始错误。
 * @returns 错误码或 `undefined`。
 */
function readErrorCode(error: unknown): number | undefined {
  if (error !== null && typeof error === 'object') {
    const raw = error as { code?: unknown; errorCode?: unknown }
    const code = typeof raw.code === 'number' ? raw.code : raw.errorCode
    if (typeof code === 'number' && Number.isFinite(code)) {
      return code
    }
  }
  return undefined
}
