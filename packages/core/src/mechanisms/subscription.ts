/**
 * 订阅基类（框架无关核心）：事件订阅（`topic` 点分小写、与后端事件表同源）。
 *
 * 来源解耦：具体总线（占位 / 本地 / 实时）由渲染插件或宿主注入；取消函数登记异步资源，
 * 释放时自动取消全部订阅。
 */

import { BaseError, ErrorCodes } from './error'
import { BaseAsyncResource, type ResourceDisposer } from './resource'

export type SubscriptionHandler = (payload: unknown, topic: string) => void

export interface SubscriptionBus {
  subscribe(topic: string, handler: SubscriptionHandler): ResourceDisposer
}

/** 占位总线（不发请求、无副作用；真实总线由宿主注入） */
export const nullSubscriptionBus: SubscriptionBus = {
  subscribe: () => () => {},
}

const TOPIC_PATTERN = /^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)+$/

export class BaseSubscription extends BaseAsyncResource {
  private readonly bus: SubscriptionBus

  constructor(bus: SubscriptionBus = nullSubscriptionBus) {
    super()
    this.bus = bus
  }

  /** 订阅（topic 点分小写校验；返回取消函数并登记释放） */
  subscribe(topic: string, handler: SubscriptionHandler): ResourceDisposer {
    if (!TOPIC_PATTERN.test(topic)) {
      throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `topic「${topic}」不符合点分小写口径`)
    }
    const unsubscribe = this.bus.subscribe(topic, handler)
    this.registerResource(unsubscribe)
    return unsubscribe
  }

  /** 释放（取消全部订阅；逆序 + 幂等由父类保证） */
  dispose(): void {
    super.dispose()
  }
}
