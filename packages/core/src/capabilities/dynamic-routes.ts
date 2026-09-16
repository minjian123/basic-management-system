/** 动态路由注册能力：菜单树 → 路由注册 / 卸载（注册动作经注入 adapter 承担，核心不依赖路由库）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'

export interface RouteRecordLike {
  name: string
  path: string
  component?: string
}

export interface DynamicRoutesAdapter {
  register(routes: readonly RouteRecordLike[]): void
  unregister(names: readonly string[]): void
}

export interface DynamicRoutesOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  adapter?: DynamicRoutesAdapter
}

export class BaseDynamicRoutes extends BaseCapability {
  private readonly adapter: DynamicRoutesAdapter | undefined

  constructor(options: DynamicRoutesOptions = {}) {
    super({ ...options, key: options.key ?? 'dynamic-routes' })
    this.adapter = options.adapter
  }

  register(routes: readonly RouteRecordLike[]): void {
    this.adapter?.register(routes)
  }

  unregister(names: readonly string[]): void {
    this.adapter?.unregister(names)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), placeholder: !this.adapter }
  }
}
