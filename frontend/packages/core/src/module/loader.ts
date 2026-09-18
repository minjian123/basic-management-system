/**
 * 本地模块加载器（**非基类实现物**，同请求层口径）：以本地模块定义表为源。
 *
 * 阶段五远端加载（Module Federation）按同一 `ModuleLoader` 接口实现，宿主装配不变。
 */

import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

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
