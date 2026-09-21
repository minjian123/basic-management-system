/**
 * 扩展点注册项（微前端模块契约）：路由·菜单 / 通用组件 / 字段渲染器 / 图标 / 工作台卡片。
 *
 * 注册项继承注册项公共契约 `BaseProvider`（组合轨），经各域注册表登记。
 */

import { BaseProvider } from '../mechanisms/provider'

/** 注册项键模式（`<命名空间>:<键>`，命名空间为模块名或平台域）。 */
export const REGISTRY_KEY_PATTERN = /^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$/

/** 页面区域标识模式（点分 `<域>.<区域>`，如 `layout.header` / `form.toolbar`）。 */
export const PAGE_AREA_ID_PATTERN = /^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$/

/** 语言标识模式（小写 BCP-47，如 `zh-cn` / `en`）。 */
export const LOCALE_TAG_PATTERN = /^[a-z]{2,3}(-[a-z0-9]{2,8})*$/

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

/** 图标注册项选项。 */
export interface IconProviderOptions {
  /** 展示名（官方图标为专有名，自定义为名称）。 */
  name?: string
  /** 分类（如 `direction` / `edit` / `media` / `common` / `custom`）。 */
  category?: string
  /** 搜索标签（中文别名等）。 */
  tags?: string[]
}

/** 图标注册项。 */
export class IconProvider extends BaseProvider {
  /** icon key（`el:User` / `biz:purchase-order` / `custom:1024` / `van:todo-o`）。 */
  readonly key: string
  /** 图标资源（组件 / SVG 文本 / 懒加载器）。 */
  readonly source: unknown
  /** 展示名。 */
  readonly name: string | undefined
  /** 分类。 */
  readonly category: string | undefined
  /** 搜索标签。 */
  readonly tags: string[]

  /**
   * 构造图标注册项。
   *
   * @param key icon key。
   * @param source 图标资源。
   * @param options 元信息（可选）。
   */
  constructor(key: string, source: unknown, options: IconProviderOptions = {}) {
    super()
    this.key = key
    this.source = source
    this.name = options.name
    this.category = options.category
    this.tags = options.tags ?? []
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

/** 页面区域注册项。 */
export class PageAreaProvider extends BaseProvider {
  /** 命名空间键（`<来源>:<区域项>`）。 */
  readonly key: string
  /** 区域标识（点分，如 `layout.header`）。 */
  readonly area: string
  /** 挂接组件（异步加载器或组件对象）。 */
  readonly component: unknown
  /** 同区域排序提示（缺省 0；保序仍以登记顺序为准）。 */
  readonly order: number

  /**
   * 构造页面区域注册项。
   *
   * @param key 命名空间键。
   * @param area 区域标识。
   * @param component 挂接组件。
   * @param order 排序提示。
   */
  constructor(key: string, area: string, component: unknown, order = 0) {
    super()
    this.key = key
    this.area = area
    this.component = component
    this.order = order
  }
}

/** 主题令牌注册项。 */
export class ThemeTokenProvider extends BaseProvider {
  /** 命名空间键（`<命名空间>:<主题标识>`）。 */
  readonly key: string
  /** 令牌映射（`--bms-*` 变量名 → 值）。 */
  readonly tokens: Record<string, string>
  /** 模式标注（`light` / `dark` / 品牌标识等，仅作检索维度）。 */
  readonly mode: string | undefined

  /**
   * 构造主题令牌注册项。
   *
   * @param key 命名空间键。
   * @param tokens 令牌映射。
   * @param mode 模式标注。
   */
  constructor(key: string, tokens: Record<string, string>, mode?: string) {
    super()
    this.key = key
    this.tokens = { ...tokens }
    this.mode = mode
  }
}

/** i18n 文案包注册项。 */
export class I18nPackProvider extends BaseProvider {
  /** 命名空间键（`<来源>:<语言标识小写>`）。 */
  readonly key: string
  /** 语言标识（小写归一，取自键的语言标识段）。 */
  readonly locale: string
  /** 文案映射（`msg_key` → 文案）。 */
  readonly messages: Record<string, string>

  /**
   * 构造 i18n 文案包注册项。
   *
   * @param key 命名空间键。
   * @param messages 文案映射。
   */
  constructor(key: string, messages: Record<string, string>) {
    super()
    this.key = key
    this.locale = key.slice(key.indexOf(':') + 1).toLowerCase()
    this.messages = { ...messages }
  }
}
