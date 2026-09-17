/** 模块上下文能力：宿主注入只读句柄（router / store / i18n / 用户 / 租户），供能力侧统一取用。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'

export interface ModuleContextHandles {
  router?: unknown
  store?: unknown
  i18n?: unknown
  user?: { id?: string; name?: string }
  tenant?: { id?: string; name?: string }
}

export interface ModuleContextOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  handles?: ModuleContextHandles
}

export class BaseModuleContext extends BaseCapability {
  private handles: ModuleContextHandles

  constructor(options: ModuleContextOptions = {}) {
    super({ ...options, key: options.key ?? 'module-context' })
    this.handles = options.handles ?? {}
  }

  /** 宿主注入（只读约定：能力侧不得改写宿主句柄） */
  provide(handles: ModuleContextHandles): void {
    this.handles = { ...this.handles, ...handles }
  }

  get<K extends keyof ModuleContextHandles>(name: K): ModuleContextHandles[K] {
    return this.handles[name]
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), provided: Object.keys(this.handles) }
  }
}
