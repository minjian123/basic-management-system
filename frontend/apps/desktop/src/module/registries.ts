/** 宿主扩展点注册表实例与平台自身注册声明（装配统一走核心装配器）。 */

import { createRegistries, type FrontendRegistries, type RegistryRegistration } from '@bms/core'

/** 前端注册表集合（平台自身注册与模块注册共用同一实例）。 */
export const registries: FrontendRegistries = createRegistries()

/** 平台自身注册声明（启动期经统一装配器倒入；随平台页面迁移逐步扩充）。 */
export const PLATFORM_REGISTRATION: RegistryRegistration = {}
