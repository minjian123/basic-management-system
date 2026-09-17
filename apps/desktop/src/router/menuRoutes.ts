/**
 * 菜单 → 路由注册（宿主编排）：统一经 `@bms/vue` 的动态路由投影 `useDynamicRoutes`（前端不硬编码路由表）。
 *
 * 占位先行：菜单树来自 `stores/menu`（占位 loader 可注入）；真实菜单随阶段七 ~ 八。
 * 叶子记录挂到布局父路由（`layout`）的 children；组件名经 `resolveView` 解析，
 * 未注册回退占位视图并开发态告警（防菜单配置错误白屏）。
 */

import type { RouteRecordRaw, Router } from 'vue-router'

import type { MenuNode, RouteRecord } from '@bms/core'
import { useDynamicRoutes } from '@bms/vue'
import { nameComponent, resolveView, type MenuItem } from '@bms/ui-ep'

import PlaceholderView from '@/views/PlaceholderView.vue'

export interface RegisterMenuRoutesOptions {
  /** 布局父路由名（菜单路由挂其 children；缺省 `layout`） */
  parentName?: string
}

const warnedNames = new Set<string>()

/** `MenuItem[]` → 动态路由片段的 `MenuNode[]` */
function toMenuNodes(items: MenuItem[]): MenuNode[] {
  return items
    .filter((item) => !item.hidden)
    .map((item) => ({
      key: item.path ?? item.name,
      title: item.name,
      ...(item.path ? { path: item.path } : {}),
      ...(item.component ? { component: item.component } : {}),
      ...(item.icon ? { icon: item.icon } : {}),
      ...(item.children ? { children: toMenuNodes(item.children) } : {}),
    }))
}

/**
 * 注册菜单路由（返回注册条数）。
 *
 * 用法（`main.ts`）：`registerMenuRoutes(router, menuStore.menus)`。
 */
export function registerMenuRoutes(
  router: Router,
  menus: MenuItem[],
  options: RegisterMenuRoutesOptions = {},
): number {
  const parentName = options.parentName ?? 'layout'
  const dynamic = useDynamicRoutes()
  const records = dynamic.buildRoutes(toMenuNodes(menus))
  let count = 0

  const registerRecord = (record: RouteRecord): void => {
    if (record.children && record.children.length > 0) {
      record.children.forEach(registerRecord)
      return
    }
    if (!record.path || record.path === '/' || router.hasRoute(record.name)) {
      return
    }
    const view = record.component ? resolveView(record.component) : null
    if (record.component && !view && import.meta.env.DEV && !warnedNames.has(record.component)) {
      warnedNames.add(record.component)
      console.warn(`[menuRoutes] 未注册的组件：${record.component}（回退占位视图）`)
    }
    const route: RouteRecordRaw = {
      name: record.name,
      path: record.path,
      component: nameComponent(record.name, view ?? PlaceholderView),
      meta: { ...record.meta, public: false },
    }
    router.addRoute(parentName, route)
    count += 1
  }

  records.forEach(registerRecord)
  return count
}
