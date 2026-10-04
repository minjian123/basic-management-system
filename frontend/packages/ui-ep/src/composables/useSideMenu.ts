/** 侧边菜单组合式：权限过滤 + 关键词过滤 + 菜单 → 路由构建 / 注册 / 卸载（经核心 `BaseDynamicRoutes`）。
 *
 * 菜单源支持**响应式**（`MaybeRef<MenuNode[]>`：常量 / `ref` / `computed`）——异步菜单（如动态菜单
 * 接口）在装载完成后自动重算过滤结果与路径清单，宿主无需重建组合式实例。
 */

import {
  BaseDynamicRoutes,
  filterMenuByKeyword,
  filterMenuByPermission,
  toRouteNodes,
  type MenuNode,
} from '@bms/core'
import { computed, ref, unref, type MaybeRef, type Ref } from 'vue'

import { useBaseAccess } from './useBaseAccess'

/** 选项。 */
export interface UseSideMenuOptions {
  /** 原始菜单树（响应式：常量 / `ref` / `computed`；异步菜单源直接可用）。 */
  menu?: MaybeRef<MenuNode[]>
  /** 权限码集合（缺省空）。 */
  codes?: Iterable<string>
  /** 权限判定（缺省使用 `codes`）。 */
  canAccess?: (code: string) => boolean
}

/** `useSideMenu` 返回面。 */
export interface UseSideMenuResult {
  /** 权限过滤后的菜单树（响应式：随 `menu` 与权限判定变化）。 */
  menu: Ref<MenuNode[]>
  /** 关键词。 */
  keyword: Ref<string>
  /** 关键词过滤后的菜单树。 */
  filtered: Ref<MenuNode[]>
  /** 设置关键词。 */
  setKeyword: (value: string) => void
  /** 已注册路由路径。 */
  routes: Ref<string[]>
  /** 由菜单树构建的路径清单（访问即按当前菜单计算）。 */
  routePaths: string[]
  /** 注册路由路径（去重、保序）。 */
  register: () => string[]
  /** 卸载路由。 */
  unregister: (path?: string) => void
  /** 权限上下文（响应式）。 */
  codes: Ref<string[]>
  /** 整体替换权限码。 */
  setCodes: (codes: Iterable<string>) => void
}

/** 具体动态路由状态（可实例化）。 */
class MenuRouteState extends BaseDynamicRoutes {}

/**
 * 使用侧边菜单。
 *
 * @param options 选项。
 * @returns 菜单状态与路由操作。
 */
export function useSideMenu(options: UseSideMenuOptions = {}): UseSideMenuResult {
  const access = useBaseAccess(options.codes ?? [])
  const canAccess =
    options.canAccess ?? (options.codes === undefined ? () => true : (code: string) => access.canAccess(code))
  const source = computed<MenuNode[]>(() => unref(options.menu) ?? [])
  const menu = computed<MenuNode[]>(() => filterMenuByPermission(source.value, canAccess))
  const keyword = ref('')
  const filtered = computed<MenuNode[]>(() => filterMenuByKeyword(menu.value, keyword.value))
  const state = new MenuRouteState()
  const routes = ref<string[]>([])
  const routePaths = computed<string[]>(() => state.build(toRouteNodes(menu.value)))

  function setKeyword(value: string): void {
    keyword.value = value
  }

  function register(): string[] {
    const paths = routePaths.value
    state.register(paths)
    routes.value = [...state.routes]
    return paths
  }

  function unregister(path?: string): void {
    state.unregister(path)
    routes.value = [...state.routes]
  }

  return {
    menu,
    keyword,
    filtered,
    setKeyword,
    routes,
    get routePaths(): string[] {
      return routePaths.value
    },
    register,
    unregister,
    codes: access.codes,
    setCodes: access.setCodes,
  }
}
