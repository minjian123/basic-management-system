/**
 * 内容页签上下文（`Tabs` 向 `TabPane` 下发的懒渲染默认值）。
 */

import type { ComputedRef, InjectionKey } from 'vue'

export const TABS_LAZY_KEY: InjectionKey<ComputedRef<boolean>> = Symbol('bms:tabs-lazy')
