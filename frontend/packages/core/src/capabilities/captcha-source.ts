/**
 * 验证码数据源插件基类与提供者注册表：验证码数据源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseCaptchaSource`，经 `CaptchaSourceRegistry` 登记接入；
 * 未登记 / 未注入时验证码能力即占位（不发请求）。
 *
 * 方法对应后端验证码出口（`app/api/captcha.py` 四端点）：
 * `POST /api/v1/captcha/challenges`、`POST /api/v1/captcha/sms`、
 * `POST /api/v1/captcha/verify`、`GET /api/v1/captcha/scenes/{scene}/policy`。
 */

import { BasePluggable } from '../mechanisms/pluggable'
import { BaseProvider } from '../mechanisms/provider'
import { BaseProviderRegistry } from '../mechanisms/registry'
import type { CaptchaKind, CaptchaScene, CaptchaTracePoint } from '../domain/captcha'

/** 出题入参（图形 / 滑块）。 */
export interface CaptchaChallengeQuery {
  /** 使用场景。 */
  scene: CaptchaScene
  /** 挑战形态（图形 / 滑块）。 */
  kind: CaptchaKind
}

/** 短信发送入参。 */
export interface CaptchaSmsQuery {
  /** 目标手机号（须已归一）。 */
  phone: string
  /** 使用场景。 */
  scene: CaptchaScene
}

/** 凭证校验入参（图形 / 短信用 `code`，滑块用 `trace`）。 */
export interface CaptchaVerifyQuery {
  /** 挑战编号。 */
  captchaId: string
  /** 挑战形态。 */
  kind: CaptchaKind
  /** 用户输入的校验码（图形 / 短信）。 */
  code?: string
  /** 滑块轨迹点序列。 */
  trace?: readonly CaptchaTracePoint[]
  /** 使用场景。 */
  scene: CaptchaScene
}

/** 场景策略入参。 */
export interface CaptchaPolicyQuery {
  /** 使用场景。 */
  scene: CaptchaScene
}

/** 数据源装载选项。 */
export interface CaptchaSourceOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/** 验证码数据源契约面（方法与 `BaseCaptchaSource` 一致；未覆写的方法返回 `undefined`，即不请求）。 */
export interface CaptchaSourceAdapter {
  /** 出题（图形 / 滑块）。 */
  challenge?(query: CaptchaChallengeQuery): Promise<unknown>
  /** 发送短信验证码。 */
  sendSms?(query: CaptchaSmsQuery): Promise<unknown>
  /** 校验凭证（判定入口；失败由后端抛业务错误码）。 */
  verify?(query: CaptchaVerifyQuery): Promise<unknown>
  /** 取场景策略（是否强制 / 失败阈值 / 有效期 / 冷却）。 */
  policy?(query: CaptchaPolicyQuery): Promise<unknown>
}

/** 验证码数据源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseCaptchaSource extends BasePluggable implements CaptchaSourceAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'captcha-source'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 出题（图形 / 滑块）。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  challenge(query: CaptchaChallengeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 发送短信验证码。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  sendSms(query: CaptchaSmsQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 校验凭证。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  verify(query: CaptchaVerifyQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 取场景策略。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  policy(query: CaptchaPolicyQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }
}

/** 数据源注册项（工厂创建插件实例）。 */
export class CaptchaSourceProvider extends BaseProvider {
  /** 数据源键（如 `http`）。 */
  readonly key: string
  /** 数据源工厂。 */
  readonly create: (options: CaptchaSourceOptions) => BaseCaptchaSource | Promise<BaseCaptchaSource>

  /**
   * 构造数据源注册项。
   *
   * @param key 数据源键。
   * @param create 数据源工厂。
   */
  constructor(key: string, create: (options: CaptchaSourceOptions) => BaseCaptchaSource | Promise<BaseCaptchaSource>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class CaptchaSourceRegistry extends BaseProviderRegistry<CaptchaSourceProvider> {
  /** 插件键。 */
  readonly pluginKey = 'captcha-source-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: CaptchaSourceProvider): string {
    return provider.key
  }
}
