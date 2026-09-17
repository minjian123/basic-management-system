/**
 * 动态路由注册能力（框架无关核心）：菜单树 → 路由构建 / 注册 / 卸载（注册动作经注入 adapter 承担，核心不依赖路由库）。
 *
 * **占位先行**：菜单树未接入时 `buildRoutes([])` 得空清单，宿主继续用静态兜底路由（不报错）。
 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

/** 路由登记最小形态（adapter 契约；`buildRoutes` 产出为 `RouteRecord`） */
export interface RouteRecordLike {
  name: string
  path: string
  component?: string
}

/** 菜单节点（后端菜单树的最小形状） */
export interface MenuNode {
  /** 菜单标识（路由名候选） */
  key: string
  title: string
  /** 路由路径（缺省由 `pathPrefix + key` 推导） */
  path?: string
  component?: string
  icon?: string
  children?: MenuNode[]
  /** 白名单标记（无需登录 / 无权限校验） */
  public?: boolean
}

/** 路由形态（与 vue-router 兼容的最小子集，核心不依赖 router 实现） */
export interface RouteRecord extends RouteRecordLike {
  meta: Record<string, unknown>
  children?: RouteRecord[]
}

export interface DynamicRoutesBuildOptions {
  /** 路由路径前缀（如 `/sys`） */
  pathPrefix?: string
  /** 允许的路径白名单（命中即不参与注册；缺省不过滤） */
  allowedPaths?: readonly string[]
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
  readonly routes = observable<readonly RouteRecordLike[]>([])
  private readonly adapter: DynamicRoutesAdapter | undefined

  constructor(options: DynamicRoutesOptions = {}) {
    super({ ...options, key: options.key ?? 'dynamic-routes' })
    this.adapter = options.adapter
  }

  /** 菜单树 → 路由记录（纯逻辑；`public` 节点与白名单路径不参与注册） */
  buildRoutes(
    menuTree: readonly MenuNode[],
    options: DynamicRoutesBuildOptions = {},
  ): RouteRecord[] {
    const prefix = options.pathPrefix ?? ''
    const allowed = options.allowedPaths ?? []
    return menuTree
      .filter((node) => !node.public && !allowed.includes(node.path ?? ''))
      .map((node) => {
        const name = node.key
        const path = node.path ?? `${prefix}/${node.key}`.replace(/\/{2,}/g, '/')
        return {
          name,
          path,
          ...(node.component ? { component: node.component } : {}),
          meta: { title: node.title, ...(node.icon ? { icon: node.icon } : {}), menuKey: node.key },
          ...(node.children && node.children.length > 0
            ? { children: this.buildRoutes(node.children, options) }
            : {}),
        }
      })
  }

  /** 登记路由（按名去重合并；有增量时通知 adapter，返回新增条数） */
  register(routes: readonly RouteRecordLike[]): number {
    const existing = new Set(this.routes.get().map((item) => item.name))
    const fresh = routes.filter((item) => !existing.has(item.name))
    if (fresh.length > 0) {
      this.routes.set([...this.routes.get(), ...fresh])
      this.adapter?.register(fresh)
    }
    return fresh.length
  }

  /** 卸载路由（缺省全部；返回移除条数） */
  unregister(names?: readonly string[]): number {
    const targets = names ?? this.routes.get().map((item) => item.name)
    const removed = this.routes.get().filter((item) => targets.includes(item.name))
    if (removed.length > 0) {
      this.routes.set(this.routes.get().filter((item) => !targets.includes(item.name)))
      this.adapter?.unregister(removed.map((item) => item.name))
    }
    return removed.length
  }

  hasRoute(name: string): boolean {
    return this.routes.get().some((item) => item.name === name)
  }

  /** 重置（先卸载全部） */
  reset(): void {
    this.unregister()
    this.routes.set([])
  }

  describe(): Record<string, unknown> {
    return {
      ...super.describe(),
      placeholder: !this.adapter,
      registered: this.routes.get().length,
    }
  }
}
