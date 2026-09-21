/**
 * 模块加载器实现（**非基类实现物**，同请求层口径）：本地定义表实现与清单驱动实现。
 *
 * 两者实现同一 `ModuleLoader` 接口——宿主只换实现通路、装配不变；远端形态（Module Federation）
 * 同样按该接口实现。
 */

import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

import type { ModuleManifestEntry } from './manifest'
import type { LoadedModule, ModuleDefinition, ModuleHostContext, ModuleLoader } from './types'

/** 本地模块加载器。 */
export class LocalModuleLoader implements ModuleLoader {
  /** 模块定义表（名 → 定义）。 */
  private readonly definitions = new Map<string, ModuleDefinition>()
  /** 已挂载模块（名 → 已加载模块）。 */
  private readonly mounted = new Map<string, LoadedModule>()

  /**
   * 构造本地模块加载器。
   *
   * @param definitions 模块定义（声明顺序即挂载顺序）。
   */
  constructor(definitions: readonly ModuleDefinition[] = []) {
    for (const definition of definitions) {
      this.definitions.set(definition.manifest.name, definition)
    }
  }

  /**
   * 注册模块定义（同名拒重）。
   *
   * @param definition 模块定义。
   * @throws BaseError 同名模块已登记（`REGISTRY_CONFLICT`）。
   */
  register(definition: ModuleDefinition): void {
    const name = definition.manifest.name
    if (this.definitions.has(name)) {
      throw new BaseError(ErrorCodes.REGISTRY_CONFLICT, `模块已登记：${name}`)
    }
    this.definitions.set(name, definition)
  }

  /**
   * 按模块名加载。
   *
   * @param name 模块名。
   * @param context 宿主上下文（缺省空）。
   * @returns 已加载模块。
   * @throws BaseError 模块未登记（`PROVIDER_NOT_REGISTERED`）。
   */
  async load(name: string, context: ModuleHostContext = {}): Promise<LoadedModule> {
    const definition = this.definitions.get(name)
    if (definition === undefined) {
      throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `模块未登记：${name}`)
    }
    const registration = await definition.setup(context)
    return { manifest: definition.manifest, registration }
  }

  /**
   * 挂载模块（重复挂载拒重）。
   *
   * @param loaded 已加载模块。
   * @throws BaseError 同名模块已挂载（`REGISTRY_CONFLICT`）。
   */
  mount(loaded: LoadedModule): void {
    const name = loaded.manifest.name
    if (this.mounted.has(name)) {
      throw new BaseError(ErrorCodes.REGISTRY_CONFLICT, `模块已挂载：${name}`)
    }
    this.mounted.set(name, loaded)
  }

  /**
   * 卸载模块（幂等）。
   *
   * @param name 模块名。
   */
  unmount(name: string): void {
    this.mounted.delete(name)
  }

  /**
   * 是否已挂载。
   *
   * @param name 模块名。
   */
  isMounted(name: string): boolean {
    return this.mounted.has(name)
  }

  /** 已挂载模块名（挂载顺序）。 */
  mountedNames(): string[] {
    return [...this.mounted.keys()]
  }

  /**
   * 读取已挂载模块。
   *
   * @param name 模块名。
   */
  getMounted(name: string): LoadedModule | undefined {
    return this.mounted.get(name)
  }
}

/** 模块入口模块（约定**默认导出**模块定义）。 */
export interface ModuleEntryModule {
  /** 默认导出（`defineModule` 产物）。 */
  default?: unknown
}

/** 模块入口懒加载表（模块标识 → 入口加载器）。 */
export type ModuleEntryTable = Record<string, () => Promise<ModuleEntryModule>>

/**
 * 判断是否为模块定义（形状校验：`manifest.name` / `manifest.version` 为字符串且 `setup` 为函数）。
 *
 * @param value 候选值。
 */
function isModuleDefinition(value: unknown): value is ModuleDefinition {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const candidate = value as { manifest?: unknown; setup?: unknown }
  const manifest = candidate.manifest
  if (typeof manifest !== 'object' || manifest === null) {
    return false
  }
  const shape = manifest as { name?: unknown; version?: unknown }
  return typeof candidate.setup === 'function' && typeof shape.name === 'string' && typeof shape.version === 'string'
}

/**
 * 清单驱动模块加载器：清单（名称 / 入口 / 版本）为唯一来源，入口经懒加载表解析。
 *
 * 加载校验（任一不过即**拒绝加载**）：清单条目存在 → 入口已登记 → 入口默认导出模块定义 →
 * 模块自报名称与版本与清单**严格一致**；上下文冻结为只读快照后交模块 `setup`。
 */
export class ManifestModuleLoader implements ModuleLoader {
  /** 清单项（保清单序）。 */
  private readonly entries: readonly ModuleManifestEntry[]
  /** 入口懒加载表。 */
  private readonly table: ModuleEntryTable
  /** 清单条目索引（名 → 条目；同名保留首个）。 */
  private readonly byName = new Map<string, ModuleManifestEntry>()
  /** 已挂载模块（名 → 已加载模块）。 */
  private readonly mounted = new Map<string, LoadedModule>()

  /**
   * 构造清单驱动加载器。
   *
   * @param entries 清单项（声明顺序即挂载顺序）。
   * @param table 入口懒加载表（入口标识 → 加载器）。
   */
  constructor(entries: readonly ModuleManifestEntry[], table: ModuleEntryTable) {
    this.entries = [...entries]
    this.table = table
    for (const entry of this.entries) {
      if (!this.byName.has(entry.name)) {
        this.byName.set(entry.name, entry)
      }
    }
  }

  /** 清单模块名（清单序）。 */
  names(): string[] {
    return this.entries.map((entry) => entry.name)
  }

  /**
   * 读取清单条目。
   *
   * @param name 模块名。
   */
  entryOf(name: string): ModuleManifestEntry | undefined {
    return this.byName.get(name)
  }

  /**
   * 按模块名加载（清单驱动；校验失败即拒绝加载）。
   *
   * @param name 模块名。
   * @param context 宿主上下文（注入前冻结为只读快照）。
   * @returns 已加载模块。
   * @throws BaseError 清单未登记 / 入口未登记（`PROVIDER_NOT_REGISTERED`），入口非模块定义 / 名称或版本不一致（`CAPABILITY_VIOLATION`）。
   */
  async load(name: string, context: ModuleHostContext = {}): Promise<LoadedModule> {
    const entry = this.byName.get(name)
    if (entry === undefined) {
      throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `模块未登记：${name}`)
    }
    const loadEntry = this.table[entry.entry]
    if (loadEntry === undefined) {
      throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `模块入口未登记：${entry.entry}`)
    }
    const loaded = (await loadEntry()) as ModuleEntryModule | undefined
    const definition = loaded?.default
    if (!isModuleDefinition(definition)) {
      throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `模块入口未默认导出模块定义：${entry.entry}`)
    }
    if (definition.manifest.name !== entry.name) {
      throw new BaseError(
        ErrorCodes.CAPABILITY_VIOLATION,
        `模块名与清单不一致：${definition.manifest.name} ≠ ${entry.name}`,
      )
    }
    if (definition.manifest.version !== entry.version) {
      throw new BaseError(
        ErrorCodes.CAPABILITY_VIOLATION,
        `模块版本与清单不一致：${entry.name} ${definition.manifest.version} ≠ ${entry.version}`,
      )
    }
    const registration = await definition.setup(Object.freeze({ ...context }))
    return {
      manifest: Object.freeze({ name: entry.name, version: entry.version, entry: entry.entry }),
      registration,
    }
  }

  /**
   * 挂载模块（重复挂载拒重）。
   *
   * @param loaded 已加载模块。
   * @throws BaseError 同名模块已挂载（`REGISTRY_CONFLICT`）。
   */
  mount(loaded: LoadedModule): void {
    const name = loaded.manifest.name
    if (this.mounted.has(name)) {
      throw new BaseError(ErrorCodes.REGISTRY_CONFLICT, `模块已挂载：${name}`)
    }
    this.mounted.set(name, loaded)
  }

  /**
   * 卸载模块（幂等）。
   *
   * @param name 模块名。
   */
  unmount(name: string): void {
    this.mounted.delete(name)
  }

  /**
   * 是否已挂载。
   *
   * @param name 模块名。
   */
  isMounted(name: string): boolean {
    return this.mounted.has(name)
  }

  /** 已挂载模块名（挂载顺序）。 */
  mountedNames(): string[] {
    return [...this.mounted.keys()]
  }

  /**
   * 读取已挂载模块。
   *
   * @param name 模块名。
   */
  getMounted(name: string): LoadedModule | undefined {
    return this.mounted.get(name)
  }
}
