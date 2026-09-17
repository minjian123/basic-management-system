/**
 * 动态路由投影（Vue 绑定插件）：核心 `BaseDynamicRoutes` ↔ Vue。
 *
 * 接口面与旧片段（宿主 `dynamic-routes`）同构：`routes` / `registered` / `buildRoutes` /
 * `register` / `unregister` / `hasRoute` / `reset`；构建与登记逻辑单份在核心。
 */

import { getCurrentScope, onScopeDispose, shallowRef, toValue, type MaybeRefOrGetter } from 'vue'

import { createCapability, type BaseDynamicRoutes, type MenuNode, type RouteRecord } from '@bms/core'

export interface UseDynamicRoutesOptions {
  /** 路由路径前缀（如 `/sys`） */
  pathPrefix?: MaybeRefOrGetter<string>
  /** 允许的路径白名单（命中即不参与注册；缺省不过滤） */
  allowedPaths?: MaybeRefOrGetter<string[]>
  /** 注册回调（宿主注入 router.addRoute / removeRoute） */
  onRegister?: (routes: RouteRecord[]) => void
  onUnregister?: (names: string[]) => void
}

export interface UseDynamicRoutesReturn {
  readonly routes: RouteRecord[]
  readonly registered: string[]
  buildRoutes: (menuTree: MenuNode[]) => RouteRecord[]
  register: (routes: RouteRecord[]) => number
  unregister: (names?: string[]) => number
  hasRoute: (name: string) => boolean
  reset: () => void
}

export function useDynamicRoutes(options: UseDynamicRoutesOptions = {}): UseDynamicRoutesReturn {
  const instance = createCapability<BaseDynamicRoutes>('dynamic-routes', {})

  const routes = shallowRef<RouteRecord[]>(instance.routes.get() as RouteRecord[])
  const unsubscribe = instance.routes.subscribe((next) => {
    routes.value = next as RouteRecord[]
  })

  if (getCurrentScope()) {
    onScopeDispose(() => {
      unsubscribe()
      instance.dispose()
    })
  }

  function unregister(names?: string[]): number {
    const before = instance.routes.get()
    const targets = names ?? before.map((item) => item.name)
    const removed = before.filter((item) => targets.includes(item.name)).map((item) => item.name)
    const count = instance.unregister(targets)
    if (removed.length > 0) {
      options.onUnregister?.(removed)
    }
    return count
  }

  return {
    get routes() {
      return routes.value
    },
    get registered() {
      return routes.value.map((item) => item.name)
    },
    buildRoutes: (menuTree) =>
      instance.buildRoutes(menuTree, {
        pathPrefix: toValue(options.pathPrefix) ?? '',
        allowedPaths: toValue(options.allowedPaths) ?? [],
      }),
    register: (incoming) => {
      const existing = new Set(instance.routes.get().map((item) => item.name))
      const fresh = flatten(incoming).filter((item) => !existing.has(item.name))
      const count = instance.register(fresh)
      if (fresh.length > 0) {
        options.onRegister?.(fresh)
      }
      return count
    },
    unregister,
    hasRoute: (name) => instance.hasRoute(name),
    reset: () => {
      unregister()
      instance.reset()
    },
  }
}

function flatten(items: readonly RouteRecord[]): RouteRecord[] {
  return items.flatMap((item) => [item, ...(item.children ? flatten(item.children) : [])])
}
