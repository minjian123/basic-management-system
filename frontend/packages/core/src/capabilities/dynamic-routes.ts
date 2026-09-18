/**
 * 动态路由能力基类：菜单树 → 路由构建 / 注册 / 卸载。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 路由节点（菜单树）。 */
export interface RouteNode {
  /** 路径。 */
  path: string
  /** 路由名（可选）。 */
  name?: string
  /** 子节点。 */
  children?: RouteNode[]
}

/** 动态路由能力基类（抽象）。 */
export abstract class BaseDynamicRoutes extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'dynamic-routes'
  /** 已注册路由路径（保序）。 */
  readonly routes: string[] = []

  /**
   * 由菜单树构建路由路径清单。
   *
   * @param menu 菜单树。
   * @returns 路由路径清单。
   */
  build(menu: readonly RouteNode[]): string[] {
    const paths: string[] = []
    const walk = (nodes: readonly RouteNode[]): void => {
      for (const node of nodes) {
        paths.push(node.path)
        if (node.children !== undefined) {
          walk(node.children)
        }
      }
    }
    walk(menu)
    return paths
  }

  /**
   * 注册路由路径（去重、保序）。
   *
   * @param paths 路由路径。
   */
  register(paths: readonly string[]): void {
    for (const path of paths) {
      if (!this.routes.includes(path)) {
        this.routes.push(path)
      }
    }
  }

  /**
   * 卸载路由（缺省卸载全部）。
   *
   * @param path 指定路径；缺省清空。
   */
  unregister(path?: string): void {
    if (path === undefined) {
      this.routes.length = 0
      return
    }
    const index = this.routes.indexOf(path)
    if (index >= 0) {
      this.routes.splice(index, 1)
    }
  }
}
