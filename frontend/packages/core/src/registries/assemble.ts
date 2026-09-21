/**
 * 统一装配器：平台自身注册与模块注册共用同一通道（登记 / 来源打标 / 校验 / 清理）。
 *
 * 两段式装配——先对全部声明校验（键模式 / 命名空间前缀 / 区域标识 / 语言标识 / 路由路径），
 * 校验全通过后再逐项倒入；倒入途中遇同键冲突则回滚本次已登记项后抛错，保证无残留。
 */

import type { ModuleRegistration } from '../module/types'

import { assertIconKey, assertLocaleTag, assertNamespacedKey, assertPageAreaId, type FrontendRegistries } from './index'
import {
  ComponentProvider,
  I18nPackProvider,
  IconProvider,
  PageAreaProvider,
  RouteMenuProvider,
  ThemeTokenProvider,
  WorkbenchCardProvider,
} from './providers'
import { schemaError } from './validate'

/** 平台自身注册的来源标识。 */
export const PLATFORM_SOURCE = 'platform'

/** 注册来源（`platform` 或模块名）。 */
export type RegistrationSource = string

/** 统一装配的注册声明（平台自身注册与模块注册同一形状）。 */
export type RegistryRegistration = ModuleRegistration

/** 登记键（`<分组>:<键>`，供卸载清理）。 */
export type RegistrationKey = string

/** 待倒入项（分组 + 键 + 已构造注册项）。 */
type PlanEntry =
  | { group: 'component'; key: string; provider: ComponentProvider }
  | { group: 'icon'; key: string; provider: IconProvider }
  | { group: 'card'; key: string; provider: WorkbenchCardProvider }
  | { group: 'region'; key: string; provider: PageAreaProvider }
  | { group: 'themeToken'; key: string; provider: ThemeTokenProvider }
  | { group: 'i18nPack'; key: string; provider: I18nPackProvider }
  | { group: 'route'; key: string; provider: RouteMenuProvider }

/**
 * 校验并构造待倒入项（校验失败即抛错，此时不产生任何登记）。
 *
 * @param source 注册来源。
 * @param registration 注册声明。
 * @returns 待倒入项清单。
 * @throws BaseError 键 / 前缀 / 区域标识 / 语言标识 / 路由路径校验失败（`CAPABILITY_VIOLATION`）。
 */
function buildPlan(source: RegistrationSource, registration: RegistryRegistration): PlanEntry[] {
  const plan: PlanEntry[] = []
  const checkKey = (key: string, scope: string): void => {
    assertNamespacedKey(key, scope)
    if (source !== PLATFORM_SOURCE && !key.startsWith(`${source}:`)) {
      throw schemaError(scope, `模块注册键须以 ${source}: 开头：${key}`)
    }
  }

  for (const [key, component] of Object.entries(registration.components ?? {})) {
    checkKey(key, '通用组件')
    plan.push({ group: 'component', key, provider: new ComponentProvider(key, component) })
  }
  for (const [key, iconSource] of Object.entries(registration.icons ?? {})) {
    checkKey(key, '图标')
    assertIconKey(key)
    plan.push({ group: 'icon', key, provider: new IconProvider(key, iconSource) })
  }
  for (const card of (registration.cards ?? []) as readonly WorkbenchCardProvider[]) {
    checkKey(card.key, '工作台卡片')
    plan.push({ group: 'card', key: card.key, provider: card })
  }
  for (const declaration of registration.regions ?? []) {
    checkKey(declaration.key, '页面区域')
    assertPageAreaId(declaration.area)
    plan.push({
      group: 'region',
      key: declaration.key,
      provider: new PageAreaProvider(declaration.key, declaration.area, declaration.component, declaration.order ?? 0),
    })
  }
  for (const declaration of registration.themeTokens ?? []) {
    checkKey(declaration.key, '主题令牌')
    plan.push({
      group: 'themeToken',
      key: declaration.key,
      provider: new ThemeTokenProvider(declaration.key, declaration.tokens, declaration.mode),
    })
  }
  for (const declaration of registration.i18nPacks ?? []) {
    checkKey(declaration.key, 'i18n 文案包')
    const provider = new I18nPackProvider(declaration.key, declaration.messages)
    assertLocaleTag(provider.locale, 'i18n 文案包')
    plan.push({ group: 'i18nPack', key: declaration.key, provider })
  }
  for (const route of registration.routes ?? []) {
    if (route.meta?.title === undefined) {
      continue
    }
    if (!route.path.startsWith('/')) {
      throw schemaError('路由·菜单', `路由路径须以 / 开头：${route.path}`)
    }
    const name = route.name ?? route.path
    plan.push({
      group: 'route',
      key: name,
      provider: new RouteMenuProvider(name, route.path, String(route.meta.title)),
    })
  }
  return plan
}

/**
 * 倒入单项（倒入前统一打来源标）。
 *
 * @param registries 前端注册表集合。
 * @param entry 待倒入项。
 * @param source 注册来源。
 */
function registerEntry(registries: FrontendRegistries, entry: PlanEntry, source: RegistrationSource): void {
  entry.provider.registrationSource = source
  switch (entry.group) {
    case 'component':
      registries.component.register(entry.provider)
      break
    case 'icon':
      registries.icon.register(entry.provider)
      break
    case 'card':
      registries.workbenchCard.register(entry.provider)
      break
    case 'region':
      registries.pageArea.register(entry.provider)
      break
    case 'themeToken':
      registries.themeToken.register(entry.provider)
      break
    case 'i18nPack':
      registries.i18nPack.register(entry.provider)
      break
    case 'route':
      registries.routeMenu.register(entry.provider)
      break
  }
}

/**
 * 统一装配（平台自身注册与模块注册共用）。
 *
 * @param registries 前端注册表集合。
 * @param source 注册来源（`platform` 或模块名）。
 * @param registration 注册声明。
 * @returns 登记键清单（供 `releaseRegistrations` 逆序清理）。
 * @throws BaseError 校验失败（`CAPABILITY_VIOLATION`）或同键冲突（`REGISTRY_CONFLICT`）。
 */
export function assembleRegistrations(
  registries: FrontendRegistries,
  source: RegistrationSource,
  registration: RegistryRegistration,
): RegistrationKey[] {
  const plan = buildPlan(source, registration)
  const keys: RegistrationKey[] = []
  try {
    for (const entry of plan) {
      registerEntry(registries, entry, source)
      keys.push(`${entry.group}:${entry.key}`)
    }
  } catch (error) {
    releaseRegistrations(registries, keys)
    throw error
  }
  return keys
}

/**
 * 逆序释放已登记键（幂等；未登记的键跳过）。
 *
 * @param registries 前端注册表集合。
 * @param keys `assembleRegistrations` 返回的登记键清单。
 */
export function releaseRegistrations(registries: FrontendRegistries, keys: readonly RegistrationKey[]): void {
  for (const entry of [...keys].reverse()) {
    const separator = entry.indexOf(':')
    const group = entry.slice(0, separator)
    const key = entry.slice(separator + 1)
    switch (group) {
      case 'component':
        registries.component.unregister(key)
        break
      case 'icon':
        registries.icon.unregister(key)
        break
      case 'card':
        registries.workbenchCard.unregister(key)
        break
      case 'region':
        registries.pageArea.unregister(key)
        break
      case 'themeToken':
        registries.themeToken.unregister(key)
        break
      case 'i18nPack':
        registries.i18nPack.unregister(key)
        break
      case 'route':
        registries.routeMenu.unregister(key)
        break
      default:
        break
    }
  }
}
