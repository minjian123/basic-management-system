/**
 * 核心契约（框架无关）：渲染插件与实现方必须满足的稳定接口面。
 *
 * 契约测试（`@bms/core/testing`）对所有实现跑同一套断言——「同接口多实现」的保障。
 */

import type { RegistryItemLike } from '../mechanisms/registry'

export * from './confirm'
export * from './menu-source'
export * from './option'
export * from './permission'
export * from './view-resolver'

/** 能力描述契约（注册项 `describe()` 下限） */
export interface CapabilityDescriptor extends RegistryItemLike {
  readonly key: string
  readonly depends: readonly string[]
}

/** 渲染插件契约（Vue / 未来引擎实现）：把核心实例投影为引擎侧可用形态 */
export interface RenderBinding<TInstance> {
  /** 取核心实例（未注册 / 未实例化时抛错） */
  use(): TInstance
}
