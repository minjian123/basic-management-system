/** 宿主扩展点注册表实例与模块注册装配（模块只声明、宿主逐项注册）。 */

import {
  ComponentProvider,
  IconProvider,
  RouteMenuProvider,
  WorkbenchCardProvider,
  createRegistries,
  schemaError,
  type FrontendRegistries,
  type ModuleRegistration,
} from '@bms/core'

/** 前端注册表集合（平台自身注册与模块注册共用同一实例）。 */
export const registries: FrontendRegistries = createRegistries()

function assertOwned(key: string, prefix: string): void {
  if (!key.startsWith(prefix)) {
    throw schemaError('模块注册', `键须以 ${prefix} 开头：${key}`)
  }
}

/**
 * 逐项倒入模块注册声明（键须属本模块命名空间）。
 *
 * @param moduleName 模块名。
 * @param registration 模块注册声明。
 * @returns 已登记键清单（按注册表分组，供卸载清理）。
 */
export function applyModuleRegistration(moduleName: string, registration: ModuleRegistration): string[] {
  const prefix = `${moduleName}:`
  const keys: string[] = []

  for (const [key, component] of Object.entries(registration.components ?? {})) {
    assertOwned(key, prefix)
    registries.component.register(new ComponentProvider(key, component))
    keys.push(`component:${key}`)
  }
  for (const [key, source] of Object.entries(registration.icons ?? {})) {
    assertOwned(key, prefix)
    registries.icon.register(new IconProvider(key, source))
    keys.push(`icon:${key}`)
  }
  for (const card of (registration.cards ?? []) as WorkbenchCardProvider[]) {
    assertOwned(card.key, prefix)
    registries.workbenchCard.register(card)
    keys.push(`card:${card.key}`)
  }
  for (const route of registration.routes ?? []) {
    const name = route.name ?? route.path
    if (route.meta?.title === undefined) {
      continue
    }
    registries.routeMenu.register(new RouteMenuProvider(name, route.path, String(route.meta.title)))
    keys.push(`route:${name}`)
  }
  return keys
}

/**
 * 清理已登记键（模块卸载）。
 *
 * @param keys `applyModuleRegistration` 返回的键清单。
 */
export function removeRegistration(keys: readonly string[]): void {
  for (const entry of keys) {
    const separator = entry.indexOf(':')
    const group = entry.slice(0, separator)
    const key = entry.slice(separator + 1)
    if (group === 'component') {
      registries.component.unregister(key)
    } else if (group === 'icon') {
      registries.icon.unregister(key)
    } else if (group === 'card') {
      registries.workbenchCard.unregister(key)
    } else if (group === 'route') {
      registries.routeMenu.unregister(key)
    }
  }
}
