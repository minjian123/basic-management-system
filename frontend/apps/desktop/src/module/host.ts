/**
 * 模块宿主装配：清单驱动加载 + 上下文注入 + 路由注册 / 卸载 + 统一装配 + 渲染消费接线。
 *
 * 加载器由「本地定义表」换为「清单驱动」（同 `ModuleLoader` 接口，装配不变）；清单 `mode`
 * 决定**入口从哪来**——`local` 走宿主本地入口表（构建期合并），`remote` 走 Module Federation
 * 运行时（运行时远端加载），两者共用同一加载器、同一校验链与同一装配 / 卸载路径；
 * 模块声明的区域 / 令牌 / 文案在挂载后生效、卸载后还原。
 */

import {
  BaseError,
  ErrorCodes,
  ManifestModuleLoader,
  PLATFORM_SOURCE,
  applyThemeTokens,
  assembleRegistrations,
  collectThemeTokens,
  releaseRegistrations,
  releaseThemeTokens,
  type LoadedModule,
  type MenuNode,
  type ModuleEntryResolver,
  type ModuleHostContext,
  type ModuleLoadMode,
  type RegistrationKey,
} from '@bms/core'

import { resolveLocalModuleEntry } from './entries'
import { createFederationEntryResolver } from './federation'
import { moduleI18n } from './i18n'
import { loadModuleManifest } from './manifest'
import { bumpRegistriesRevision, PLATFORM_REGISTRATION, registries } from './registries'
import { setModuleError } from './boundary'
import { documentThemeTarget } from './themeTokens'

import { router } from '@/router'
import { registerModuleRoutes, unregisterModuleRoutes } from '@/router/dynamic'

/** 清单装载结果汇总。 */
export interface ModuleInstallSummary {
  /** 已挂载模块名。 */
  mounted: string[]
  /** 失败模块（名 / 版本 / 原因）。 */
  failures: { name: string; version: string; reason: string }[]
}

/** 当前加载器（清单装载后可用）。 */
let loader: ManifestModuleLoader | undefined

/** 模块路由名（模块名 → 路由名清单）。 */
const mountedRoutes = new Map<string, string[]>()
/** 模块登记键（模块名 → 登记键清单）。 */
const registrationKeys = new Map<string, RegistrationKey[]>()
/** 模块令牌名（模块名 → 已写入令牌名）。 */
const themeTokenNames = new Map<string, string[]>()
/** 模块文案包键（模块名 → 已并入键）。 */
const i18nKeys = new Map<string, string[]>()

/**
 * 平台自身注册（启动期；与模块注册共用同一通道）。
 *
 * @returns 登记键清单。
 */
export function installPlatformRegistrations(): RegistrationKey[] {
  return assembleRegistrations(registries, PLATFORM_SOURCE, PLATFORM_REGISTRATION)
}

/** 当前模块加载器（清单装载后可用）。 */
export function getModuleLoader(): ManifestModuleLoader | undefined {
  return loader
}

/**
 * 装载模块清单并逐条挂载（启动期调用一次）。
 *
 * 清单获取失败按空清单继续（记错误状态，不阻塞启动）；单条失败记错误状态并归集，其余照常。
 *
 * @param context 宿主上下文（各模块共用）。
 * @returns 装载结果汇总。
 */
export async function installModules(context: ModuleHostContext = {}): Promise<ModuleInstallSummary> {
  const manifest = await loadModuleManifest()
  if (manifest.reason !== undefined) {
    setModuleError({ module: 'modules.json', version: '', reason: manifest.reason })
  }
  for (const rejection of manifest.rejected) {
    setModuleError({ module: rejection.name, version: '', reason: rejection.reason })
  }

  const resolvers: Record<ModuleLoadMode, ModuleEntryResolver> = {
    local: resolveLocalModuleEntry,
    remote: createFederationEntryResolver(),
  }
  loader = new ManifestModuleLoader(manifest.entries, (entry) => resolvers[entry.mode](entry))
  const summary: ModuleInstallSummary = { mounted: [], failures: [] }
  for (const entry of manifest.entries) {
    try {
      await mountModule(entry.name, context)
      summary.mounted.push(entry.name)
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      setModuleError({ module: entry.name, version: entry.version, reason })
      summary.failures.push({ name: entry.name, version: entry.version, reason })
    }
  }
  return summary
}

/**
 * 加载并挂载模块（按模块名注册路由、扩展点与渲染消费接线；失败回滚本次已产生的接线）。
 *
 * @param name 模块名。
 * @param context 宿主上下文。
 * @returns 已加载模块。
 * @throws BaseError 清单未装载（`PROVIDER_NOT_REGISTERED`）或加载 / 装配失败。
 */
export async function mountModule(name: string, context: ModuleHostContext = {}): Promise<LoadedModule> {
  const active = loader
  if (active === undefined) {
    throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, '模块清单未装载')
  }
  const loaded = await active.load(name, context)
  active.mount(loaded)
  try {
    mountedRoutes.set(name, registerModuleRoutes(router, loaded.registration.routes ?? []))
    registrationKeys.set(name, assembleRegistrations(registries, name, loaded.registration))
    themeTokenNames.set(name, applyThemeTokens(documentThemeTarget(), collectThemeTokens(registries.themeToken)))
    i18nKeys.set(name, moduleI18n.merge(loaded.registration.i18nPacks ?? []))
    bumpRegistriesRevision()
    return loaded
  } catch (error) {
    unmountModule(name)
    throw error
  }
}

/**
 * 卸载模块（逆序：路由 → 文案 → 令牌 → 注册表 → 加载器；幂等）。
 *
 * @param name 模块名。
 */
export function unmountModule(name: string): void {
  unregisterModuleRoutes(router, mountedRoutes.get(name) ?? [])
  mountedRoutes.delete(name)

  moduleI18n.restore(i18nKeys.get(name) ?? [])
  i18nKeys.delete(name)

  releaseThemeTokens(documentThemeTarget(), themeTokenNames.get(name) ?? [])
  themeTokenNames.delete(name)

  releaseRegistrations(registries, registrationKeys.get(name) ?? [])
  registrationKeys.delete(name)

  loader?.unmount(name)
  bumpRegistriesRevision()
}

/**
 * 菜单节点（取自**路由·菜单注册表快照**，登记序）。
 *
 * @returns 菜单节点。
 */
export function moduleMenuNodes(): MenuNode[] {
  return registries.routeMenu.values().map((provider) => ({
    path: provider.path,
    title: provider.title,
    name: provider.key,
    icon: provider.icon ?? 'sparkles',
  }))
}
