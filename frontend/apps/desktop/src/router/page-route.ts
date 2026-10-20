/**
 * 通用页面路由接线（宿主）：表单页声明 → 路由装载 + 清单适配器装配。
 *
 * - 单例 `pageRoute`（`BasePageRoute` 具体实例）持有平台表单页声明，并接数据源清单（`/data-sources`）
 *   与表单标识清单（`/form-keys`）适配器；会话就绪后 `load()`；
 * - `ensureFormPageRoutes` 统一装载表单页路由（幂等；跳过已存在路径）、`uninstallFormPageRoutes`
 *   随会话清理卸载；装载顺序须在菜单占位路由（`ensureMenuRoutes`）之前，避免同路径重复注册。
 */

import { BasePageRoute, type FormPageDeclaration, type PageRouteResolution } from '@bms/core'
import type { Router } from 'vue-router'

import { fetchDataSourceList, fetchFormKeyList } from '@/api/registry'

/** 具体页面路由（可实例化）。 */
class PlatformPageRoute extends BasePageRoute {}

/** 通用页面路由单例（宿主装配；清单适配器随装配注入）。 */
export const pageRoute = new PlatformPageRoute()

pageRoute.adapter = {
  loadDataSources: () => fetchDataSourceList(),
  loadFormKeys: () => fetchFormKeyList(),
}

/** 平台表单页声明（表单标识 → 页面；路径 / 名 / 元信息与既有静态路由一致）。 */
export const FORM_PAGE_DECLARATIONS: FormPageDeclaration[] = [
  {
    formKey: 'role',
    title: '角色管理',
    path: '/sys/roles',
    name: 'SystemRole',
    meta: { keepAlive: true },
    list: () => import('@/views/system/RoleView.vue'),
  },
  {
    formKey: 'user',
    title: '用户管理',
    path: '/sys/users',
    name: 'SystemUser',
    meta: { keepAlive: true },
    list: () => import('@/views/system/user/UserView.vue'),
  },
  {
    formKey: 'tenant',
    title: '租户管理',
    path: '/sys/tenants',
    name: 'SystemTenant',
    meta: { keepAlive: true },
    list: () => import('@/views/system/TenantView.vue'),
  },
]

pageRoute.declareAll(FORM_PAGE_DECLARATIONS)

/** 本模块装载的表单页路由名（幂等依据与卸载清单）。 */
let installedRouteNames: string[] = []

/**
 * 统一装载表单页路由（幂等；跳过已存在路径）。
 *
 * @param router 路由实例。
 * @returns 已装载的路由名清单。
 */
export function ensureFormPageRoutes(router: Router): string[] {
  if (installedRouteNames.length === 0) {
    for (const declaration of FORM_PAGE_DECLARATIONS) {
      const name = declaration.name ?? declaration.path
      if (router.getRoutes().some((route) => route.path === declaration.path)) {
        continue
      }
      router.addRoute({
        path: declaration.path,
        name,
        component: declaration.list as () => Promise<unknown>,
        meta: { title: declaration.title, ...(declaration.meta ?? {}) },
      })
      installedRouteNames.push(name)
    }
  }
  return installedRouteNames
}

/**
 * 卸载表单页路由（会话清理：登出 / 失效）。
 *
 * @param router 路由实例。
 */
export function uninstallFormPageRoutes(router: Router): void {
  for (const name of installedRouteNames) {
    if (router.hasRoute(name)) {
      router.removeRoute(name)
    }
  }
  installedRouteNames = []
}

/**
 * 按表单标识解析页面（供页面按 `form_key` 寻址）。
 *
 * @param formKey 表单标识。
 * @returns 解析结果；未声明 / 数据源未登记返回 `undefined`。
 */
export function resolvePageRoute(formKey: string): PageRouteResolution | undefined {
  return pageRoute.resolve(formKey)
}
