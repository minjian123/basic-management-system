/** 模块宿主装配：本地模块加载器 + 宿主上下文注入 + 路由注册 / 卸载 + 统一装配。 */

import {
  LocalModuleLoader,
  PLATFORM_SOURCE,
  assembleRegistrations,
  releaseRegistrations,
  type LoadedModule,
  type MenuNode,
  type ModuleHostContext,
  type RegistrationKey,
} from '@bms/core'

import { demoModule } from '@/modules/demo'
import { router } from '@/router'
import { registerModuleRoutes, unregisterModuleRoutes } from '@/router/dynamic'
import { PLATFORM_REGISTRATION, registries } from './registries'

const loader = new LocalModuleLoader([demoModule])
const mountedRoutes = new Map<string, string[]>()
const registrationKeys = new Map<string, RegistrationKey[]>()

/**
 * 平台自身注册（启动期；与模块注册共用同一通道）。
 *
 * @returns 登记键清单。
 */
export function installPlatformRegistrations(): RegistrationKey[] {
  return assembleRegistrations(registries, PLATFORM_SOURCE, PLATFORM_REGISTRATION)
}

/** 模块加载器实例（阶段五换远端实现，装配不变）。 */
export function getModuleLoader(): LocalModuleLoader {
  return loader
}

/**
 * 加载并挂载模块（按模块名注册其路由与扩展点）。
 *
 * @param name 模块名。
 * @param context 宿主上下文。
 * @returns 已加载模块。
 */
export async function mountModule(name: string, context: ModuleHostContext = {}): Promise<LoadedModule> {
  const loaded = await loader.load(name, context)
  loader.mount(loaded)
  mountedRoutes.set(name, registerModuleRoutes(router, loaded.registration.routes ?? []))
  registrationKeys.set(name, assembleRegistrations(registries, name, loaded.registration))
  return loaded
}

/**
 * 卸载模块（移除其路由与扩展点登记，幂等）。
 *
 * @param name 模块名。
 */
export function unmountModule(name: string): void {
  unregisterModuleRoutes(router, mountedRoutes.get(name) ?? [])
  mountedRoutes.delete(name)
  releaseRegistrations(registries, registrationKeys.get(name) ?? [])
  registrationKeys.delete(name)
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
