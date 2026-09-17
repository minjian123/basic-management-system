/**
 * 视图解析注入点（`FormFrame` 动态表单视图用）。
 *
 * 契约在 `@bms/core`（`ViewResolver<TView>`，框架无关）；本插件专化为 Vue `Component`。
 *
 * - `nameComponent`：包装组件并固定 `name`（keep-alive 按路由 name 精确缓存），纯 Vue 实现；
 * - `resolveView`：视图名 → 异步组件，宿主经 `configureViewResolver` 注入（`@/views` 文件名映射
 *   属宿主职责）；**未注入 = 未注册**（返回 `null`，调用方回退占位视图），占位保真。
 */

import { createViewResolverService, type ViewResolver as CoreViewResolver } from '@bms/core'
import { defineAsyncComponent, defineComponent, h, type Component } from 'vue'

type ViewLoader = () => Promise<{ default: Component }>

export type ViewResolver = CoreViewResolver<Component>

const service = createViewResolverService<Component>()

/** 注入视图解析器（传 `undefined` 恢复未注入） */
export function configureViewResolver(next: ViewResolver | undefined): void {
  service.configure(next)
}

/** 视图名 → 异步组件（未注入 / 未注册返回 `null`） */
export function resolveView(name: string): Component | null {
  return service.resolve(name)
}

/** 包装组件并固定 `name`（keep-alive 按标签 key = 路由 name 精确缓存） */
export function nameComponent(
  name: string,
  source: Component | (() => Promise<unknown>),
): Component {
  const inner =
    typeof source === 'function'
      ? defineAsyncComponent(source as ViewLoader)
      : source
  return defineComponent({
    name,
    render: () => h(inner as Component),
  })
}
