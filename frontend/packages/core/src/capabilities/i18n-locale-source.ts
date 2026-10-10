/**
 * 启用语言清单插件基类与提供者注册表：语言清单为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseI18nLocaleSource`，经 `I18nLocaleSourceRegistry` 登记接入；
 * 未登记 / 未注入时语言清单即占位（不发请求，字段仅必填语言可编辑并提示）。
 *
 * 契约对应后端「启用语言清单只读出口」（登录即可）与当前登录用户语言：
 * `GET /api/v1/i18n/locales/enabled`（code / name / 默认标记 / rtl）+ 会话语言。
 * 语言清单驱动多语言文案字段的语言行——新增语言只需在语言清单启用，界面与接口契约都不变。
 */

import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'

/** 语言清单数据源契约面（未覆写的方法返回 `undefined`，即不请求）。 */
export interface I18nLocaleSourceAdapter {
  /** 取启用语言清单（含默认语言标记与 rtl）。 */
  loadEnabledLocales?(): Promise<unknown>
  /** 取当前登录用户语言。 */
  currentUserLocale?(): string | undefined
}

/** 语言清单数据源装载选项。 */
export interface I18nLocaleSourceOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
  /** 当前登录用户语言（静态值或取值函数；决定必填语言）。 */
  userLocale?: string | (() => string)
}

/** 启用语言清单插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseI18nLocaleSource extends BasePluggable implements I18nLocaleSourceAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'i18n-locale-source'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 取启用语言清单。
   *
   * @returns 原始结果（缺省 `undefined`）。
   */
  loadEnabledLocales(): Promise<unknown> {
    return Promise.resolve(undefined)
  }

  /**
   * 取当前登录用户语言。
   *
   * @returns 语言标识（缺省 `undefined`）。
   */
  currentUserLocale(): string | undefined {
    return undefined
  }
}

/** 语言清单数据源工厂（按装载选项产出插件实例）。 */
export type I18nLocaleSourceFactory = (options: I18nLocaleSourceOptions) => BaseI18nLocaleSource | Promise<BaseI18nLocaleSource>

/** 语言清单数据源注册项（工厂创建插件实例）。 */
export class I18nLocaleSourceProvider extends BaseProvider {
  /** 数据源键（如 `http`）。 */
  readonly key: string
  /** 数据源工厂。 */
  readonly create: I18nLocaleSourceFactory

  /**
   * 构造语言清单数据源注册项。
   *
   * @param key 数据源键。
   * @param create 数据源工厂。
   */
  constructor(key: string, create: I18nLocaleSourceFactory) {
    super()
    this.key = key
    this.create = create
  }
}

/** 语言清单数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class I18nLocaleSourceRegistry extends BaseProviderRegistry<I18nLocaleSourceProvider> {
  /** 插件键。 */
  readonly pluginKey = 'i18n-locale-source-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: I18nLocaleSourceProvider): string {
    return provider.key
  }
}
