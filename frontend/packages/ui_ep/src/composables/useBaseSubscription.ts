/** 订阅投影：把核心订阅基类 `BaseSubscription` 投影为组合式（点分主题订阅 / 广播 / 释放自动取消）。 */

import { BaseSubscription } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 订阅处理器。 */
export type SubscriptionHandler = (payload: unknown) => void

/** 具体订阅件（可实例化；取消函数登记为异步资源，释放时自动取消）。 */
class SubscriptionState extends BaseSubscription {
  /** 主题 → 处理器集合。 */
  readonly #listeners = new Map<string, Set<SubscriptionHandler>>()

  /**
   * 订阅主题。
   *
   * @param topic 主题（点分小写）。
   * @param handler 处理器。
   * @returns 取消函数（幂等）。
   */
  subscribe(topic: string, handler: SubscriptionHandler): () => void {
    const set = this.#listeners.get(topic) ?? new Set<SubscriptionHandler>()
    set.add(handler)
    this.#listeners.set(topic, set)
    const off = (): void => {
      set.delete(handler)
    }
    this.registerDisposable({ dispose: off })
    return off
  }

  /**
   * 广播主题消息（占位总线：本地分发）。
   *
   * @param topic 主题。
   * @param payload 载荷。
   */
  emit(topic: string, payload: unknown): void {
    for (const handler of [...(this.#listeners.get(topic) ?? [])]) {
      try {
        handler(payload)
      } catch (error) {
        this.reportError(error, { scope: 'useBaseSubscription.emit' })
      }
    }
  }

  /** 已订阅主题。 */
  get topicList(): string[] {
    return [...this.#listeners.keys()]
  }
}

/** `useBaseSubscription` 返回面。 */
export interface UseBaseSubscriptionResult {
  /** 订阅基类实例。 */
  subscription: BaseSubscription
  /** 已订阅主题（响应式）。 */
  topics: Ref<string[]>
  /** 订阅主题。 */
  subscribe: (topic: string, handler: SubscriptionHandler) => () => void
  /** 广播主题消息。 */
  emit: (topic: string, payload: unknown) => void
}

/**
 * 使用订阅投影。
 *
 * @returns 订阅基类实例与响应式面。
 */
export function useBaseSubscription(): UseBaseSubscriptionResult {
  const subscription = new SubscriptionState()
  const topics = ref<string[]>(subscription.topicList)
  onScopeDispose(() => {
    subscription.dispose()
  })

  return {
    subscription,
    topics,
    subscribe: (topic, handler) => {
      const off = subscription.subscribe(topic, handler)
      topics.value = subscription.topicList
      return () => {
        off()
        topics.value = subscription.topicList
      }
    },
    emit: (topic, payload) => subscription.emit(topic, payload),
  }
}
