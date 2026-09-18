/**
 * 扩展点注册项（微前端模块契约）：路由·菜单 / 通用组件 / 字段渲染器 / 图标 / 工作台卡片。
 *
 * 注册项继承注册项公共契约 `BaseProvider`（组合轨），经各域注册表登记。
 */

import { BaseProvider } from '../mechanisms/provider'

/** 注册项键模式（`<命名空间>:<键>`，命名空间为模块名或平台域）。 */
export const REGISTRY_KEY_PATTERN = /^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$/

/** 路由·菜单注册项（键为路由名）。 */
export class RouteMenuProvider extends BaseProvider {
  /** 路由名。 */
  readonly key: string
  /** 路由路径（须以 `/` 开头）。 */
  readonly path: string
  /** 菜单标题。 */
  readonly title: string
  /** 图标名。 */
  readonly icon: string | undefined

  /**
   * 构造路由·菜单注册项。
   *
   * @param key 路由名。
   * @param path 路由路径。
   * @param title 菜单标题。
   * @param icon 图标名。
   */
  constructor(key: string, path: string, title: string, icon?: string) {
    super()
    this.key = key
    this.path = path
    this.title = title
    this.icon = icon
  }
}

/** 通用组件注册项。 */
export class ComponentProvider extends BaseProvider {
  /** 命名空间键。 */
  readonly key: string
  /** 组件（异步加载器或组件对象）。 */
  readonly component: unknown

  /**
   * 构造通用组件注册项。
   *
   * @param key 命名空间键。
   * @param component 组件。
   */
  constructor(key: string, component: unknown) {
    super()
    this.key = key
    this.component = component
  }
}

/** 字段渲染器注册项。 */
export class FieldRendererProvider extends BaseProvider {
  /** 命名空间键。 */
  readonly key: string
  /** 组件。 */
  readonly component: unknown
  /** 字段类型（可选，用于按类型解析）。 */
  readonly fieldType: string | undefined

  /**
   * 构造字段渲染器注册项。
   *
   * @param key 命名空间键。
   * @param component 组件。
   * @param fieldType 字段类型。
   */
  constructor(key: string, component: unknown, fieldType?: string) {
    super()
    this.key = key
    this.component = component
    this.fieldType = fieldType
  }
}

/** 图标注册项。 */
export class IconProvider extends BaseProvider {
  /** 命名空间键。 */
  readonly key: string
  /** 图标资源。 */
  readonly source: unknown

  /**
   * 构造图标注册项。
   *
   * @param key 命名空间键。
   * @param source 图标资源。
   */
  constructor(key: string, source: unknown) {
    super()
    this.key = key
    this.source = source
  }
}

/** 工作台卡片注册项。 */
export class WorkbenchCardProvider extends BaseProvider {
  /** 命名空间键。 */
  readonly key: string
  /** 卡片组件。 */
  readonly component: unknown
  /** 卡片标题。 */
  readonly title: string | undefined

  /**
   * 构造工作台卡片注册项。
   *
   * @param key 命名空间键。
   * @param component 卡片组件。
   * @param title 卡片标题。
   */
  constructor(key: string, component: unknown, title?: string) {
    super()
    this.key = key
    this.component = component
    this.title = title
  }
}
