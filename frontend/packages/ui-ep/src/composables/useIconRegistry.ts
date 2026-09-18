/** 图标注册表接入：活动注册表（默认本地实例，宿主可注入覆盖）与来源解析辅助。 */

import { BaseProviderRegistry, IconRegistry } from '@bms/core'

/** 本地默认注册表（未注入宿主实例时使用）。 */
const localRegistry = new IconRegistry()

/** 当前活动注册表。 */
let activeRegistry: IconRegistry = localRegistry

/**
 * 校验注册表基于统一注册表基座（链上接入；类型守卫）。
 *
 * @param registry 待校验对象。
 */
export function isIconRegistryBase(registry: unknown): registry is IconRegistry {
  return registry instanceof BaseProviderRegistry
}

/**
 * 注入宿主图标注册表（宿主装配时调用）。
 *
 * @param registry 注册表实例。
 */
export function setIconRegistry(registry: IconRegistry): void {
  activeRegistry = registry
}

/** 取当前活动注册表。 */
export function getIconRegistry(): IconRegistry {
  return activeRegistry
}

/**
 * 使用图标注册表（组件传入优先，否则取活动注册表）。
 *
 * @param override 组件级覆盖。
 */
export function useIconRegistry(override?: IconRegistry): IconRegistry {
  return override ?? activeRegistry
}

/** 重置为本地默认注册表（测试用）。 */
export function resetIconRegistry(): void {
  activeRegistry = localRegistry
}
