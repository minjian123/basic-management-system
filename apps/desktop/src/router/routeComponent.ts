/**
 * 路由组件工具：组件名约定（`keep-alive :include` 以**路由 name** 匹配）与视图解析。
 *
 * - `nameComponent(name, source)`：包装组件并**固定 name**（静态路由与动态菜单路由一致处理）；
 * - `resolveView(name)`：`@/views/**\/*.vue` 文件名映射（未命中返回 `null`，由调用方回退占位视图）。
 */

import { defineAsyncComponent, defineComponent, h, type Component } from 'vue'

const viewModules = import.meta.glob('../views/**/*.vue')

type ViewLoader = () => Promise<{ default: Component }>

/** 视图名 → 异步组件（未注册返回 `null`） */
export function resolveView(name: string): Component | null {
  for (const [path, loader] of Object.entries(viewModules)) {
    const file = path.split('/').pop() ?? ''
    if (file.replace(/\.vue$/, '') === name) {
      return defineAsyncComponent(loader as ViewLoader)
    }
  }
  return null
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
