/**
 * 动态路由接线：占位菜单树 → 路由注册（基于核心 `BaseDynamicRoutes`）。
 *
 * 菜单（按用户上下文）路由经 `ensureMenuRoutes` **幂等装载**、`uninstallMenuRoutesAll` **全量卸载**，
 * 由宿主在会话就绪 / 会话清理时调用（域五 `05_03`）；产品模块路由另行注册，不随会话清理。
 */

import { BaseDynamicRoutes, findMenuByPath, flattenMenu, toRouteNodes, type MenuNode, type ModuleRouteDeclaration } from '@bms/core'
import type { Router } from 'vue-router'

/** 具体动态路由注册器（可实例化）。 */
class MenuRouteRegistry extends BaseDynamicRoutes {}

/** 占位路由名。 */
const PLACEHOLDER_VIEW = () => import('@/views/PlaceholderView.vue')

/** 本模块装载的菜单占位路由路径（幂等依据与卸载清单）。 */
let installedMenuPaths: string[] = []

/**
 * 依据菜单树注册占位路由（跳过静态已存在路径与根路径）。
 *
 * @param router 路由实例。
 * @param menu 菜单树（缺省 `/` 与已存在路由不注册）。
 * @returns 本次注册的路径清单。
 */
export function installMenuRoutes(router: Router, menu: readonly MenuNode[]): string[] {
  const registry = new MenuRouteRegistry()
  const paths = registry.build(toRouteNodes(menu))
  const registered: string[] = []

  for (const path of paths) {
    if (path === '/' || router.hasRoute(path)) {
      continue
    }
    const node = findMenuByPath(menu, path)
    router.addRoute({
      path,
      name: path,
      component: PLACEHOLDER_VIEW,
      meta: { title: node?.title ?? '' },
    })
    registered.push(path)
  }

  registry.register(registered)
  return registered
}

/**
 * 卸载菜单占位路由。
 *
 * @param router 路由实例。
 * @param paths 路径清单（缺省卸载全部菜单占位路由）。
 */
export function uninstallMenuRoutes(router: Router, paths: readonly string[]): void {
  for (const path of paths) {
    if (router.hasRoute(path)) {
      router.removeRoute(path)
    }
  }
}

/**
 * 幂等装载菜单动态路由（已装载直接返回，不重复注册）。
 *
 * @param router 路由实例。
 * @param menu 菜单树（会话就绪时的用户上下文菜单；阶段七前为占位菜单）。
 * @returns 已装载的路径清单。
 */
export function ensureMenuRoutes(router: Router, menu: readonly MenuNode[]): string[] {
  if (installedMenuPaths.length === 0) {
    installedMenuPaths = installMenuRoutes(router, menu)
  }
  return installedMenuPaths
}

/**
 * 卸载本模块装载的全部菜单动态路由（会话清理：登出 / 失效）。
 *
 * @param router 路由实例。
 */
export function uninstallMenuRoutesAll(router: Router): void {
  uninstallMenuRoutes(router, installedMenuPaths)
  installedMenuPaths = []
}

/**
 * 占位菜单树全部可注册路径（供调试 / 后续真实菜单替换）。
 *
 * @param menu 菜单树。
 * @returns 路径清单。
 */
export function menuPaths(menu: readonly MenuNode[]): string[] {
  return flattenMenu(menu).map((node) => node.path)
}

/**
 * 注册模块路由声明（跳过根路径与已存在路由名）。
 *
 * @param router 路由实例。
 * @param routes 模块路由声明。
 * @returns 本次注册的**路由名**清单（卸载按名进行）。
 */
export function registerModuleRoutes(router: Router, routes: readonly ModuleRouteDeclaration[]): string[] {
  const registered: string[] = []
  for (const route of routes) {
    const name = route.name ?? route.path
    if (route.path === '/' || router.hasRoute(name)) {
      continue
    }
    router.addRoute({
      path: route.path,
      name,
      component: route.component as () => Promise<unknown>,
      meta: { ...(route.meta ?? {}) },
    })
    registered.push(name)
  }
  return registered
}

/**
 * 卸载模块路由（按路由名）。
 *
 * @param router 路由实例。
 * @param names 路由名清单。
 */
export function unregisterModuleRoutes(router: Router, names: readonly string[]): void {
  for (const name of names) {
    if (router.hasRoute(name)) {
      router.removeRoute(name)
    }
  }
}
