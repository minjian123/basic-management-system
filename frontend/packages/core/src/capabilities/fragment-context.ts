/** 片段上下文能力：宿主注入只读句柄（router / store / i18n / 用户 / 租户），供能力侧统一取用。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'

export interface FragmentContextHandles {
  router?: unknown
  store?: unknown
  i18n?: unknown
  user?: { id?: string; name?: string }
  tenant?: { id?: string; name?: string }
}

export interface FragmentContextOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  handles?: FragmentContextHandles
}

export class BaseFragmentContext extends BaseCapability {
  private handles: FragmentContextHandles

  constructor(options: FragmentContextOptions = {}) {
    super({ ...options, key: options.key ?? 'fragment-context' })
    this.handles = options.handles ?? {}
  }

  /** 宿主注入（只读约定：能力侧不得改写宿主句柄） */
  provide(handles: FragmentContextHandles): void {
    this.handles = { ...this.handles, ...handles }
  }

  get<K extends keyof FragmentContextHandles>(name: K): FragmentContextHandles[K] {
    return this.handles[name]
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), provided: Object.keys(this.handles) }
  }
}
