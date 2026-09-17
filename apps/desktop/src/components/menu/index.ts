/**
 * 组件域出口：侧边菜单（`src/components/menu/`）。
 *
 * 契约见《组件设计 · 侧边菜单》：`SideMenu` / `MenuNode`；数据层为 `stores/menu.ts`
 * （占位 loader 可注入，真实菜单接口随阶段七 ~ 八）。
 */

export { default as SideMenu } from './SideMenu.vue'
export { default as MenuNode } from './MenuNode.vue'
export type { MenuItem } from './types'
