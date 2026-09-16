/**
 * 组件域出口：侧边菜单（`ui-ep/src/components/menu/`）。
 */

export { default as MenuNode } from './MenuNode.vue'
export { default as SideMenu } from './SideMenu.vue'
export { configureMenuSource, getMenuSource, type MenuSourceProvider } from './menuSource'
export {
  filterMenuTree,
  findAncestorKeys,
  menuKey,
  sortVisible,
  type MenuItem,
} from './types'
