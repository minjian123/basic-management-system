/**
 * 动态路由片段（`dynamic-routes`）：菜单树 → 路由的构建、注册、卸载与守卫协作。
 *
 * 契约见《组件设计 · 动态路由片段》：`buildRoutes` / `register` / `unregister` / `hasRoute` /
 * `reset`（前端不硬编码路由表；配合宿主薄壳与注册表基座）。
 * **占位先行**：菜单树未接入时 `buildRoutes([])` 得空清单，宿主继续用静态兜底路由（不报错）。
 * 注册表协作：路由登记可经注册表基座（`BaseRegistry`）承载，本片段只维护路由对象清单。
 */

import { computed, ref, type MaybeRefOrGetter, toValue } from 'vue'

import { declareFragment } from '../fragments'

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

/** 路由形态（与 vue-router 兼容的最小子集，避免片段强依赖 router 实现） */
export interface RouteRecord {
  name: string
  path: string
  component?: string
  meta: Record<string, unknown>
  children?: RouteRecord[]
}

/** 动态路由片段参数 */
export interface UseDynamicRoutesOptions {
  /** 路由模式（`menu` 菜单驱动 / `hybrid` 菜单 + 本地叠加） */
  mode?: MaybeRefOrGetter<'menu' | 'hybrid'>
  /** 路由路径前缀（如 `/sys`） */
  pathPrefix?: MaybeRefOrGetter<string>
  /** 允许的路径白名单（命中即不参与注册；缺省不过滤） */
  allowedPaths?: MaybeRefOrGetter<string[]>
  /** 404 兜底路由名（未注册路由命中时使用） */
  fallback404?: MaybeRefOrGetter<string>
  /** 注册回调（宿主注入 router.addRoute / removeRoute） */
  onRegister?: (routes: RouteRecord[]) => void
  onUnregister?: (names: string[]) => void
}

/** 动态路由片段返回值 */
export interface UseDynamicRoutesReturn {
  readonly routes: RouteRecord[]
  readonly registered: string[]
  buildRoutes: (menuTree: MenuNode[]) => RouteRecord[]
  register: (routes: RouteRecord[]) => number
  unregister: (names?: string[]) => number
  hasRoute: (name: string) => boolean
  reset: () => void
}

/**
 * 获取动态路由能力。
 *
 * 用法：`const routes = useDynamicRoutes({ onRegister: (list) => list.forEach((r) => router.addRoute(r)) })`；
 * `register(buildRoutes(menuTree))` 即完成菜单 → 路由的挂接。
 */
export function useDynamicRoutes(options: UseDynamicRoutesOptions = {}): UseDynamicRoutesReturn {
  const capability = declareFragment('dynamic-routes')

  const routes = ref<RouteRecord[]>([])
  const allowed = computed(() => toValue(options.allowedPaths) ?? [])

  const buildRoutes = (menuTree: MenuNode[]): RouteRecord[] => {
    const prefix = String(toValue(options.pathPrefix) ?? '')
    return menuTree
      .filter((node) => !node.public && !allowed.value.includes(node.path ?? ''))
      .map((node) => {
        const name = node.key
        const path = node.path ?? `${prefix}/${node.key}`.replace(/\/{2,}/g, '/')
        return {
          name,
          path,
          ...(node.component ? { component: node.component } : {}),
          meta: { title: node.title, ...(node.icon ? { icon: node.icon } : {}), menuKey: node.key },
          ...(node.children && node.children.length > 0 ? { children: buildRoutes(node.children) } : {}),
        }
      })
  }

  const flatten = (items: RouteRecord[]): RouteRecord[] =>
    items.flatMap((item) => [item, ...(item.children ? flatten(item.children) : [])])

  const register = (incoming: RouteRecord[]): number => {
    const all = flatten(incoming)
    const existing = new Set(routes.value.map((item) => item.name))
    const fresh = all.filter((item) => !existing.has(item.name))
    routes.value = [...routes.value, ...fresh]
    if (fresh.length > 0) {
      options.onRegister?.(fresh)
    }
    capability.log('debug', `dynamic-routes 注册 ${fresh.length} 条（共 ${routes.value.length} 条）`)
    return fresh.length
  }

  const unregister = (names?: string[]): number => {
    const targets = names ?? routes.value.map((item) => item.name)
    const removed = routes.value.filter((item) => targets.includes(item.name))
    routes.value = routes.value.filter((item) => !targets.includes(item.name))
    if (removed.length > 0) {
      options.onUnregister?.(removed.map((item) => item.name))
    }
    return removed.length
  }

  return {
    get routes() {
      return routes.value
    },
    get registered() {
      return routes.value.map((item) => item.name)
    },
    buildRoutes,
    register,
    unregister,
    hasRoute: (name) => routes.value.some((item) => item.name === name),
    reset: () => {
      unregister()
      routes.value = []
    },
  }
}
