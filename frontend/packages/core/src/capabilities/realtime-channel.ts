/**
 * 实时通道插件基类与提供者注册表：实时通道为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseRealtimeChannel`，经 `RealtimeChannelRegistry` 登记接入；
 * 未登记 / 未注入时通知能力即轮询占位（不发请求）。
 */

import type { NotificationConnectionState, NotificationRealtimePayload } from '../domain/notification'
import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'

/** 实时通道插件基类（抽象；方法与 `NotificationRealtimeAdapter` 契约一致）。 */
export abstract class BaseRealtimeChannel extends BasePluggable {
  /** 插件键。 */
  readonly pluginKey: string = 'realtime-channel'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /** 建立连接。 */
  abstract connect(): void

  /** 断开连接（幂等）。 */
  abstract disconnect(): void

  /**
   * 订阅连接状态。
   *
   * @param handler 状态回调。
   * @returns 取消函数。
   */
  abstract onState(handler: (state: NotificationConnectionState) => void): () => void

  /**
   * 订阅实时消息。
   *
   * @param handler 消息回调。
   * @returns 取消函数。
   */
  abstract onMessage(handler: (payload: NotificationRealtimePayload) => void): () => void
}

/** 实时通道注册项（工厂创建插件实例）。 */
export class RealtimeChannelProvider extends BaseProvider {
  /** 通道键（如 `socket.io`）。 */
  readonly key: string
  /** 通道工厂。 */
  readonly create: () => BaseRealtimeChannel

  /**
   * 构造实时通道注册项。
   *
   * @param key 通道键。
   * @param create 通道工厂。
   */
  constructor(key: string, create: () => BaseRealtimeChannel) {
    super()
    this.key = key
    this.create = create
  }
}

/** 实时通道注册表（统一注册表基座；同键唯一性拒重）。 */
export class RealtimeChannelRegistry extends BaseProviderRegistry<RealtimeChannelProvider> {
  /** 插件键。 */
  readonly pluginKey = 'realtime-channel-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: RealtimeChannelProvider): string {
    return provider.key
  }
}
