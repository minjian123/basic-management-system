/** 菜单状态契约（框架无关）：非受控模式下宿主注入的菜单状态提供者接口面。 */

/** 菜单项（后端 `GET /menus/my` 下发结构的最小集） */
export interface MenuItem {
  /** 菜单名（后端按 locale 下发 i18n 文案） */
  name: string
  /** 路由 path（叶子菜单必填） */
  path?: string
  /** 路由组件名（菜单 → 路由注册用；缺省占位视图） */
  component?: string
  /** 图标 key（`IconDisplay` 回补前不渲染） */
  icon?: string
  /** 排序（升序） */
  sort?: number
  /** 不上菜单但可用于路由 */
  hidden?: boolean
  /** 徽标（可选；占位与传统口径默认不配——角标统一放顶栏） */
  badge?: string | number
  /** 外链（新开窗口） */
  external?: boolean
  children?: MenuItem[]
}

export interface MenuSourceProvider {
  /** 可见菜单树（已过滤 hidden / 排序） */
  visibleMenus: () => MenuItem[]
  /** 展开集（非受控初始展开） */
  expandedKeys: () => string[]
  /** 记录某键展开态变更 */
  setExpanded: (key: string, open: boolean) => void
  /** 展开目标 path 的祖先链 */
  expandByPath: (path: string) => void
}
