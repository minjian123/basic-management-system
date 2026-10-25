/**
 * 启用语言清单数据源：HTTP 内建实现 + 注册表默认实例（`fetch` 单一落点）。
 *
 * 契约：`GET {端点}/i18n/locales/enabled`（**登录即可**，见《概要设计 · 国际化管理》接口表），
 * 返回启用语言清单（`code` / `name` / 默认语言标记 / `rtl`）；当前登录用户语言由宿主经
 * `userLocale` 注入（缺省取请求头解析结果）。宿主可经 `registerI18nLocaleSource` 登记定制实现
 * 或覆盖内建键；未注入即占位零请求（字段仅必填语言可编辑并提示）。
 */

import {
  BaseError,
  BaseI18nLocaleSource,
  I18nLocaleSourceProvider,
  I18nLocaleSourceRegistry,
  type I18nLocaleSourceFactory,
  type I18nLocaleSourceOptions,
} from '@bms/core'

/** 链路内默认语言清单数据源注册表实例（宿主可登记定制实现或覆盖内建键）。 */
export const i18nLocaleSourceRegistry = new I18nLocaleSourceRegistry()

/**
 * 登记语言清单数据源实现。
 *
 * @param key 数据源键（同键拒重）。
 * @param create 数据源工厂。
 */
export function registerI18nLocaleSource(key: string, create: I18nLocaleSourceFactory): void {
  i18nLocaleSourceRegistry.register(new I18nLocaleSourceProvider(key, create))
}

/** HTTP 内建启用语言清单数据源。 */
class HttpI18nLocaleSource extends BaseI18nLocaleSource {
  /** 实现名。 */
  override readonly pluginName: string = 'http'
  /** 装载选项（端点 / 请求头 / 当前登录用户语言）。 */
  readonly #options: I18nLocaleSourceOptions

  /**
   * 构造 HTTP 数据源。
   *
   * @param options 装载选项。
   */
  constructor(options: I18nLocaleSourceOptions = {}) {
    super()
    this.#options = options
  }

  /**
   * 取启用语言清单。
   *
   * @returns 原始结果（无 `fetch` 能力时降级 `undefined`）。
   */
  override async loadEnabledLocales(): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      return undefined
    }
    const endpoint = (this.#options.endpoint ?? '/api/v1').replace(/\/+$/, '')
    const response = await fetchFn(`${endpoint}/i18n/locales/enabled`, {
      method: 'GET',
      headers: this.#headers(),
    })
    return unwrapResponse(await readJson(response), response.ok)
  }

  /**
   * 取当前登录用户语言。
   *
   * @returns 语言标识（未注入时 `undefined`）。
   */
  override currentUserLocale(): string | undefined {
    const configured = this.#options.userLocale
    if (typeof configured === 'function') {
      const value = configured()
      return value === '' ? undefined : value
    }
    return configured === '' ? undefined : configured
  }

  /**
   * 解析请求头（静态对象或取值函数）。
   *
   * @returns 请求头。
   */
  #headers(): Record<string, string> {
    return typeof this.#options.headers === 'function' ? this.#options.headers() : (this.#options.headers ?? {})
  }
}

/**
 * 创建 HTTP 内建启用语言清单数据源。
 *
 * @param options 装载选项。
 * @returns 数据源实例。
 */
export function createHttpI18nLocaleSource(options: I18nLocaleSourceOptions = {}): BaseI18nLocaleSource {
  return new HttpI18nLocaleSource(options)
}

/** 登记内建 HTTP 数据源（默认键，宿主可覆盖）。 */
registerI18nLocaleSource('http', createHttpI18nLocaleSource)

/**
 * 读取响应 JSON（解析失败返回 `undefined`）。
 *
 * @param response 响应对象。
 * @returns 响应体。
 */
async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

/**
 * 解统一响应包装（`{ code, message, data }`；非包装原样返回；业务码非 0 / 200 抛错）。
 *
 * @param payload 原始响应体。
 * @param ok HTTP 是否成功（非包装且失败时抛通用错误）。
 * @returns 数据体。
 */
function unwrapResponse(payload: unknown, ok: boolean): unknown {
  if (payload !== null && typeof payload === 'object' && !Array.isArray(payload)) {
    const record = payload as { code?: unknown; message?: unknown; data?: unknown }
    if (typeof record.code === 'number') {
      if (record.code !== 0 && record.code !== 200) {
        throw new BaseError(record.code, typeof record.message === 'string' ? record.message : '')
      }
      return record.data
    }
  }
  if (!ok) {
    throw new BaseError(40208, '语言清单服务不可用')
  }
  return payload
}
