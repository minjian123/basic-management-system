/**
 * 新体系装配（S5a 试点切流）：ui-ep 注入点接线。
 *
 * - 权限判定：`configurePermissionChecker` ← 权限应用态 store（任意 / 全量语义）；
 * - 菜单状态：`configureMenuSource` ← 菜单 store（可见菜单 / 展开集持久化归 store）；
 * - 视图解析：`configureViewResolver` ← 路由视图工具（`@/views` 文件名映射）。
 *
 * 在 `app.use(createPinia())` 之后调用（store 经闭包懒取，确保运行期有激活 pinia）。
 */

import { configureMenuSource, configurePermissionChecker, configureViewResolver } from '@bms/ui-ep'

import { resolveView } from '@/router/routeComponent'
import { useMenuStore } from '@/stores/menu'
import { usePermissionStore } from '@/stores/permission'

export function bootstrapUiBridge(): void {
  configurePermissionChecker((codes, mode) => {
    const store = usePermissionStore()
    return mode === 'all' ? store.hasAll([...codes]) : store.hasAny([...codes])
  })

  configureViewResolver(resolveView)

  configureMenuSource({
    visibleMenus: () => useMenuStore().visibleMenus,
    expandedKeys: () => useMenuStore().expandedKeys,
    setExpanded: (key, open) => useMenuStore().setExpanded(key, open),
    expandByPath: (path) => {
      useMenuStore().expandByPath(path)
    },
  })
}
