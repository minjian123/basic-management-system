/**
 * 验证码数据源：HTTP 内建实现 + 注册表默认实例（`fetch` 单一落点）。
 *
 * 端点与后端验证码出口同源（`/api/v1/captcha/challenges|sms|verify|scenes/{scene}/policy`，
 * 见 `app/api/captcha.py` 四端点与 `NullCaptcha` 占位）；宿主可经 `registerCaptchaSource`
 * 登记定制实现或覆盖内建键。业务错误码（20101 ~ 20103）在解包时抛 `BaseError`，由族基类映射文案。
 */

import {
  BaseCaptchaSource,
  BaseError,
  CaptchaSourceProvider,
  CaptchaSourceRegistry,
  buildCaptchaChallengeQuery,
  buildCaptchaSmsQuery,
  buildCaptchaVerifyQuery,
  normalizeCaptchaScene,
  type CaptchaChallengeQuery,
  type CaptchaPolicyQuery,
  type CaptchaSmsQuery,
  type CaptchaSourceOptions,
  type CaptchaVerifyQuery,
} from '@bms/core'

/** 链路内默认验证码数据源注册表实例（宿主可登记定制实现或覆盖内建键）。 */
export const captchaSourceRegistry = new CaptchaSourceRegistry()

/**
 * 登记验证码数据源实现。
 *
 * @param key 数据源键（同键拒重）。
 * @param create 数据源工厂。
 */
export function registerCaptchaSource(
  key: string,
  create: (options: CaptchaSourceOptions) => BaseCaptchaSource | Promise<BaseCaptchaSource>,
): void {
  captchaSourceRegistry.register(new CaptchaSourceProvider(key, create))
}

/** HTTP 内建验证码数据源（未覆盖的方法不请求）。 */
class HttpCaptchaSource extends BaseCaptchaSource {
  /** 实现名。 */
  override readonly pluginName: string = 'http'
  /** 装载选项（端点 / 请求头）。 */
  readonly #options: CaptchaSourceOptions

  /**
   * 构造 HTTP 数据源。
   *
   * @param options 装载选项。
   */
  constructor(options: CaptchaSourceOptions = {}) {
    super()
    this.#options = options
  }

  /**
   * 出题（图形 / 滑块）。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async challenge(query: CaptchaChallengeQuery): Promise<unknown> {
    return this.#post('/captcha/challenges', buildCaptchaChallengeQuery(query))
  }

  /**
   * 发送短信验证码。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async sendSms(query: CaptchaSmsQuery): Promise<unknown> {
    return this.#post('/captcha/sms', buildCaptchaSmsQuery(query))
  }

  /**
   * 校验凭证。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async verify(query: CaptchaVerifyQuery): Promise<unknown> {
    return this.#post('/captcha/verify', buildCaptchaVerifyQuery(query))
  }

  /**
   * 取场景策略。
   *
   * @param query 查询入参。
   * @returns 原始结果。
   */
  override async policy(query: CaptchaPolicyQuery): Promise<unknown> {
    const scene = normalizeCaptchaScene(query.scene) ?? 'login'
    return this.#get(`/captcha/scenes/${encodeURIComponent(scene)}/policy`)
  }

  /**
   * POST 请求并解统一响应包装。
   *
   * @param path 路径（相对端点前缀）。
   * @param body 请求体（JSON）。
   * @returns 数据体（无 `fetch` 能力时降级 `undefined`）。
   */
  async #post(path: string, body: Record<string, unknown>): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      return undefined
    }
    const headers = { 'content-type': 'application/json', ...this.#headers() }
    const response = await fetchFn(this.#url(path), { method: 'POST', headers, body: JSON.stringify(body) })
    return unwrapResponse(await readJson(response), response.ok)
  }

  /**
   * GET 请求并解统一响应包装。
   *
   * @param path 路径（相对端点前缀）。
   * @returns 数据体（无 `fetch` 能力时降级 `undefined`）。
   */
  async #get(path: string): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      return undefined
    }
    const response = await fetchFn(this.#url(path), { method: 'GET', headers: this.#headers() })
    return unwrapResponse(await readJson(response), response.ok)
  }

  /**
   * 拼接请求地址（端点前缀 + 路径）。
   *
   * @param path 路径。
   * @returns 完整地址。
   */
  #url(path: string): string {
    const endpoint = (this.#options.endpoint ?? '/api/v1').replace(/\/+$/, '')
    return `${endpoint}${path}`
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
 * 创建 HTTP 内建验证码数据源。
 *
 * @param options 装载选项。
 * @returns 数据源实例。
 */
export function createHttpCaptchaSource(options: CaptchaSourceOptions = {}): BaseCaptchaSource {
  return new HttpCaptchaSource(options)
}

/** 登记内建 HTTP 数据源（默认键，宿主可覆盖）。 */
registerCaptchaSource('http', createHttpCaptchaSource)

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
    throw new BaseError(20101, '验证码服务不可用')
  }
  return payload
}
