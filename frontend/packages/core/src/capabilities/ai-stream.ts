/**
 * AI 流式插件基类与提供者注册表：AI 流式通道为**可替换实现（纵向）**——
 * 内建 SSE 实现继承 `BaseAiStream`，经 `AiStreamRegistry` 登记接入；
 * 未登记 / 未注入时 AI 能力即占位（不发请求）。
 */

import type { AiChatRequest, AiStreamHandlers } from './ai-assistant'
import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'

/** AI 流式请求（与 `AiStreamAdapter.start` 入参一致）。 */
export interface AiStreamInput {
  /** 请求载荷。 */
  request: AiChatRequest
  /** 流式回调。 */
  handlers: AiStreamHandlers
}

/** AI 流式插件基类（抽象；方法与 `AiStreamAdapter` 契约一致）。 */
export abstract class BaseAiStream extends BasePluggable {
  /** 插件键。 */
  readonly pluginKey: string = 'ai-stream'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 发起一次流式对话。
   *
   * @param input 请求与回调。
   * @returns 可中止句柄。
   */
  abstract start(input: AiStreamInput): { abort(): void }
}

/** AI 流式注册项（工厂创建插件实例）。 */
export class AiStreamProvider extends BaseProvider {
  /** 流式键（如 `sse`）。 */
  readonly key: string
  /** 流式工厂。 */
  readonly create: () => BaseAiStream

  /**
   * 构造 AI 流式注册项。
   *
   * @param key 流式键。
   * @param create 流式工厂。
   */
  constructor(key: string, create: () => BaseAiStream) {
    super()
    this.key = key
    this.create = create
  }
}

/** AI 流式注册表（统一注册表基座；同键唯一性拒重）。 */
export class AiStreamRegistry extends BaseProviderRegistry<AiStreamProvider> {
  /** 插件键。 */
  readonly pluginKey = 'ai-stream-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: AiStreamProvider): string {
    return provider.key
  }
}
