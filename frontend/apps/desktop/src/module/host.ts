/** 模块宿主装配：本地模块加载器 + 宿主上下文注入 + 路由注册 / 卸载 + 菜单派生。 */

import { LocalModuleLoader, type LoadedModule, type MenuNode, type ModuleHostContext } from '@bms/core'

import { demoModule } from '@/modules/demo'
import { router } from '@/router'
import { registerModuleRoutes, unregisterModuleRoutes } from '@/router/dynamic'

const loader = new LocalModuleLoader([demoModule])
const mountedRoutes = new Map<string, string[]>()

/** 模块加载器实例（阶段五换远端实现，装配不变）。 */
export function getModuleLoader(): LocalModuleLoader {
  return loader
}

/**
 * 加载并挂载模块（注册其路由）。
 *
 * @param name 模块名。
 * @param context 宿主上下文。
 * @returns 已加载模块。
 */
export async function mountModule(name: string, context: ModuleHostContext = {}): Promise<LoadedModule> {
  const loaded = await loader.load(name, context)
  loader.mount(loaded)
  mountedRoutes.set(name, registerModuleRoutes(router, loaded.registration.routes ?? []))
  return loaded
}

/**
 * 卸载模块（移除其路由，幂等）。
 *
 * @param name 模块名。
 */
export function unmountModule(name: string): void {
  unregisterModuleRoutes(router, mountedRoutes.get(name) ?? [])
  mountedRoutes.delete(name)
  loader.unmount(name)
}

/**
 * 派生模块菜单节点（取自注册声明的路由元信息）。
 *
 * @param name 模块名。
 * @returns 菜单节点（无 `meta.title` 的路由不参与）。
 */
export function moduleMenuNodes(name: string): MenuNode[] {
  const loaded = loader.getMounted(name)
  return (loaded?.registration.routes ?? [])
    .filter((route) => route.meta?.title !== undefined)
    .map((route) => ({
      path: route.path,
      title: String(route.meta?.title ?? route.path),
      name: route.name,
      icon: 'sparkles',
    }))
}
