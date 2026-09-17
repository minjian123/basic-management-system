/**
 * 视图解析契约（框架无关）：`FormFrame` 动态表单视图的宿主注入接口面。
 *
 * `TView` 泛型化——渲染插件侧专化（`ui-ep` 为 Vue `Component`），核心不依赖 Vue 类型。
 */

export type ViewResolver<TView = unknown> = (name: string) => TView | null
