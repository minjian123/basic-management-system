/**
 * 扩展点注册表（微前端模块契约）：五个具体注册表与工厂。
 *
 * 均基于统一提供者注册表基座 `BaseProviderRegistry`（同键唯一性拒重、保序、只读快照），
 * 供模块注册与平台自身注册共用——**不得另起映射**。
 */

import { schemaError } from './validate'

import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

import {
  ComponentProvider,
  FieldRendererProvider,
  IconProvider,
  REGISTRY_KEY_PATTERN,
  RouteMenuProvider,
  WorkbenchCardProvider,
} from './providers'

export * from './providers'
export { schemaError }

/** 校验命名空间键（模块注册项）。 */
export function assertNamespacedKey(key: string, scope: string): void {
  if (!REGISTRY_KEY_PATTERN.test(key)) {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `${scope} 注册键非法：${key}`)
  }
}

/** icon key 模式（`el:User` / `biz:purchase-order` / `custom:1024` / `van:todo-o`）。 */
export const ICON_KEY_PATTERN = /^[a-z][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._-]*$/

/**
 * 校验 icon key（前缀 + 大小写/数字/连字符段）。
 *
 * @param key icon key。
 * @throws BaseError 键非法（`CAPABILITY_VIOLATION`）。
 */
export function assertIconKey(key: string): void {
  if (!ICON_KEY_PATTERN.test(key)) {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `图标键非法：${key}`)
  }
}

/** 归一化图标检索文本（小写、去分隔符，保留中英文；kebab/Pascal 归一后可匹配）。 */
function normalizeIconSearch(value: string): string {
  return value.toLowerCase().replace(/[\s:._-]+/g, '')
}

/** 路由·菜单注册表。 */
export class RouteMenuRegistry extends BaseProviderRegistry<RouteMenuProvider> {
  /** 插件键。 */
  readonly pluginKey = 'route-menu-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: RouteMenuProvider): string {
    return provider.key
  }

  /**
   * 登记路由·菜单（路径须以 `/` 开头）。
   *
   * @param provider 注册项。
   */
  override register(provider: RouteMenuProvider): void {
    if (!provider.path.startsWith('/')) {
      throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `路由路径须以 / 开头：${provider.path}`)
    }
    super.register(provider)
  }
}

/** 通用组件注册表。 */
export class ComponentRegistry extends BaseProviderRegistry<ComponentProvider> {
  /** 插件键。 */
  readonly pluginKey = 'component-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: ComponentProvider): string {
    return provider.key
  }

  /**
   * 登记通用组件（键须为命名空间键）。
   *
   * @param provider 注册项。
   */
  override register(provider: ComponentProvider): void {
    assertNamespacedKey(provider.key, '通用组件')
    super.register(provider)
  }
}

/** 字段渲染器注册表。 */
export class FieldRendererRegistry extends BaseProviderRegistry<FieldRendererProvider> {
  /** 插件键。 */
  readonly pluginKey = 'field-renderer-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: FieldRendererProvider): string {
    return provider.key
  }

  /**
   * 登记字段渲染器（键须为命名空间键）。
   *
   * @param provider 注册项。
   */
  override register(provider: FieldRendererProvider): void {
    assertNamespacedKey(provider.key, '字段渲染器')
    super.register(provider)
  }

  /**
   * 按字段类型解析渲染器（首个命中）。
   *
   * @param fieldType 字段类型。
   */
  resolveByType(fieldType: string): FieldRendererProvider | undefined {
    return this.values().find((provider) => provider.fieldType === fieldType)
  }
}

/** 图标注册表。 */
export class IconRegistry extends BaseProviderRegistry<IconProvider> {
  /** 插件键。 */
  readonly pluginKey = 'icon-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: IconProvider): string {
    return provider.key
  }

  /**
   * 登记图标（键须为 icon key：`前缀:段`，段允许大小写 / 数字 / `._-`）。
   *
   * @param provider 注册项。
   */
  override register(provider: IconProvider): void {
    assertIconKey(provider.key)
    super.register(provider)
  }

  /**
   * 按来源前缀取图标（`el` / `biz` / `custom` / `van`，冒号可省）。
   *
   * @param prefix 来源前缀。
   */
  byPrefix(prefix: string): IconProvider[] {
    const normalized = prefix.endsWith(':') ? prefix : `${prefix}:`
    return this.values().filter((provider) => provider.key.startsWith(normalized))
  }

  /**
   * 按关键词检索（归一匹配 key / name / tags；空串返回全部）。
   *
   * @param keyword 关键词。
   */
  search(keyword: string): IconProvider[] {
    const text = normalizeIconSearch(keyword)
    if (text === '') {
      return this.values()
    }
    return this.values().filter((provider) => {
      const key = normalizeIconSearch(provider.key)
      const name = normalizeIconSearch(provider.name ?? '')
      const tags = provider.tags.map((tag) => normalizeIconSearch(tag))
      return key.includes(text) || name.includes(text) || tags.some((tag) => tag.includes(text))
    })
  }

  /**
   * 解析图标资源（未登记返回 `undefined`）。
   *
   * @param key icon key。
   */
  resolve(key: string): unknown {
    return this.get(key)?.source
  }
}

/** 工作台卡片注册表。 */
export class WorkbenchCardRegistry extends BaseProviderRegistry<WorkbenchCardProvider> {
  /** 插件键。 */
  readonly pluginKey = 'workbench-card-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: WorkbenchCardProvider): string {
    return provider.key
  }

  /**
   * 登记工作台卡片（键须为命名空间键）。
   *
   * @param provider 注册项。
   */
  override register(provider: WorkbenchCardProvider): void {
    assertNamespacedKey(provider.key, '工作台卡片')
    super.register(provider)
  }
}

/** 前端注册表集合。 */
export interface FrontendRegistries {
  /** 路由·菜单。 */
  routeMenu: RouteMenuRegistry
  /** 通用组件。 */
  component: ComponentRegistry
  /** 字段渲染器。 */
  fieldRenderer: FieldRendererRegistry
  /** 图标。 */
  icon: IconRegistry
  /** 工作台卡片。 */
  workbenchCard: WorkbenchCardRegistry
}

/**
 * 创建前端注册表集合（平台自身注册与模块注册共用同一实例）。
 *
 * @returns 注册表集合。
 */
export function createRegistries(): FrontendRegistries {
  return {
    routeMenu: new RouteMenuRegistry(),
    component: new ComponentRegistry(),
    fieldRenderer: new FieldRendererRegistry(),
    icon: new IconRegistry(),
    workbenchCard: new WorkbenchCardRegistry(),
  }
}
