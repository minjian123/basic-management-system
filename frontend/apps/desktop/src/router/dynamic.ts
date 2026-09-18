/** 动态路由接线：占位菜单树 → 路由注册（基于核心 `BaseDynamicRoutes`）。 */

import { BaseDynamicRoutes, findMenuByPath, flattenMenu, toRouteNodes, type MenuNode } from '@bms/core'
import type { Router } from 'vue-router'

/** 具体动态路由注册器（可实例化）。 */
class MenuRouteRegistry extends BaseDynamicRoutes {}

/** 占位路由名。 */
const PLACEHOLDER_VIEW = () => import('@/views/PlaceholderView.vue')

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
 * 占位菜单树全部可注册路径（供调试 / 后续真实菜单替换）。
 *
 * @param menu 菜单树。
 * @returns 路径清单。
 */
export function menuPaths(menu: readonly MenuNode[]): string[] {
  return flattenMenu(menu).map((node) => node.path)
}
