/**
 * 扫码登录状态源插件基类与提供者注册表：状态源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseSsoQrSource`，经 `SsoQrSourceRegistry` 登记接入；
 * 未登记 / 未注入时扫码登录能力即占位（不发请求）。
 *
 * 方法对应后端扫码链路出口（域二 `02_04`）：
 * `GET /api/v1/auth/sso/{idp_key}/authorize-url`（取授权 URL）。
 * **本期无扫码状态端点**（后端不做轮询状态机），`poll` 为可注入的扩展面：
 * 真实平台适配（内嵌登录组件 / 状态端点）归阶段十七，届时换实现即可。
 */

import { BasePluggable } from '../mechanisms/pluggable'
import { BaseProvider } from '../mechanisms/provider'
import { BaseProviderRegistry } from '../mechanisms/registry'

/** 取授权 URL 入参。 */
export interface SsoQrInitQuery {
  /** IdP 标识。 */
  idpKey: string
  /** 租户编码（可选；缺省由后端按上下文 / 子域名解析）。 */
  tenant?: string | null
}

/** 轮询入参。 */
export interface SsoQrPollQuery {
  /** IdP 标识。 */
  idpKey: string
  /** 租户编码（可选）。 */
  tenant?: string | null
  /** 流程状态（一次性）。 */
  state: string
  /** 连续失败次数（自 1 起）。 */
  attempt: number
}

/** 状态源装载选项。 */
export interface SsoQrSourceOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/** 状态源契约面（方法与 `BaseSsoQrSource` 一致；未覆写的方法返回 `undefined`，即不请求）。 */
export interface SsoQrLoginSourceAdapter {
  /** 取授权 URL（返回 `{ authorize_url, state, expires_in }`）。 */
  init?(query: SsoQrInitQuery): Promise<unknown>
  /** 轮询扫码状态（返回 `{ status, redirect? }`）。 */
  poll?(query: SsoQrPollQuery): Promise<unknown>
}

/** 状态源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseSsoQrSource extends BasePluggable implements SsoQrLoginSourceAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'sso-qr-source'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 取授权 URL。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  init(query: SsoQrInitQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 轮询扫码状态。
   *
   * @param query 查询入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  poll(query: SsoQrPollQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }
}

/** 状态源注册项（工厂创建插件实例）。 */
export class SsoQrSourceProvider extends BaseProvider {
  /** 状态源键（如 `http`）。 */
  readonly key: string
  /** 状态源工厂。 */
  readonly create: (options?: SsoQrSourceOptions) => BaseSsoQrSource | Promise<BaseSsoQrSource>

  /**
   * 构造状态源注册项。
   *
   * @param key 状态源键。
   * @param create 状态源工厂。
   */
  constructor(key: string, create: (options?: SsoQrSourceOptions) => BaseSsoQrSource | Promise<BaseSsoQrSource>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 状态源注册表（统一注册表基座；同键唯一性拒重）。 */
export class SsoQrSourceRegistry extends BaseProviderRegistry<SsoQrSourceProvider> {
  /** 插件键。 */
  readonly pluginKey = 'sso-qr-source-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: SsoQrSourceProvider): string {
    return provider.key
  }
}
