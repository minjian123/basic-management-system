/**
 * 订阅基类：事件订阅的统一语义——注册 / 取消 / 占位实现 / 来源解耦。
 *
 * 对齐后端事件域与实时推送的**消费侧**：`topic` 取后端事件表（点分小写，`领域.动作`），
 * 前端不新造事件名。真实实时推送（Socket.IO）随阶段五接入；接入前绑「占位总线」——
 * `subscribe` 正常注册（不连 socket、不报错），`publish` 仅本地生效，接入后 `setSource` 切换，
 * **调用方不改**。取消函数自动登记异步资源，组件卸载即取消。
 * 依赖方向单向：只依赖组件根（含机制装配点）。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import { BaseComponent, warnUnattachedMechanism, type ComponentBaseOptions, type MechanismLike } from './BaseComponent'
import { BaseAsyncResource } from './resource'

/** 订阅来源：实时推送 / 本地总线 / 占位总线（缺省按接入阶段自动选择） */
export type SubscriptionSource = 'realtime' | 'local' | 'placeholder'

/** 事件处理（`payload` 为后端推送数据） */
export type SubscriptionHandler = (payload: unknown) => void

/** 订阅基类构造参数 */
export interface SubscriptionOptions extends ComponentBaseOptions {
  /** 订阅来源，默认 `placeholder`（未接后端推送时的占位总线） */
  source?: SubscriptionSource
  /** 事件名校验（默认点分小写：`领域.动作`） */
  topicPattern?: RegExp
  /** 释放异常回调（透传内部异步资源） */
  onError?: (error: unknown) => void
  /** 组件根（传入即构造时挂接，免去显式 `mechanisms.attach`） */
  owner?: BaseComponent
}

/** 机制标识 */
export const SUBSCRIPTION_MECHANISM_KEY = 'subscription'

/** 事件名口径：点分小写（《命名规范》「基础设施命名」节 Socket.IO 事件） */
export const DEFAULT_TOPIC_PATTERN = /^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)+$/

/**
 * 订阅基类：注册 / 取消 / 单次订阅 / 本地发布，来源可切换。
 *
 * 取消函数经内部异步资源登记（`kind = 'subscription'`），组件卸载自动取消且幂等。
 */
export class BaseSubscription extends BaseComponent implements MechanismLike {
  readonly mechanismKey = SUBSCRIPTION_MECHANISM_KEY

  private readonly handlers = new Map<string, Set<SubscriptionHandler>>()
  private readonly topicPattern: RegExp
  private readonly resources: BaseAsyncResource
  private sourceValue: SubscriptionSource
  private attached = false

  constructor(options: SubscriptionOptions = {}) {
    super(options)
    this.topicPattern = options.topicPattern ?? DEFAULT_TOPIC_PATTERN
    this.sourceValue = options.source ?? 'placeholder'
    // 内部异步资源：承载取消函数的登记与释放（自身即组件根子类，随订阅一起挂接）
    this.resources = new BaseAsyncResource({
      ns: this.ns,
      identifier: `${this.identifier}#resources`,
      ...(options.onError ? { onError: options.onError } : {}),
      owner: this,
    })
    if (options.owner) {
      options.owner.mechanisms.attach(this)
    }
    if (options.source === 'realtime') {
      this.setSource('realtime')
    }
  }

  /** 当前订阅来源 */
  get source(): SubscriptionSource {
    return this.sourceValue
  }

  /** 已订阅事件名（去重） */
  get topics(): readonly string[] {
    return [...this.handlers.keys()]
  }

  /**
   * 切换订阅来源。
   *
   * `realtime` 未接入（阶段五前）时：开发态告警并回落 `placeholder`，**不报错**——
   * 保证「替换来源不改调用方」。
   */
  setSource(source: SubscriptionSource): void {
    this.warnIfUnattached()
    if (source === 'realtime') {
      this.log('warn', 'subscription: 实时推送未接入（随阶段五），回落占位总线')
      this.sourceValue = 'placeholder'
      return
    }
    this.sourceValue = source
  }

  /** 订阅事件，返回**幂等**取消函数（已登记异步资源，卸载自动取消） */
  subscribe(topic: string, handler: SubscriptionHandler): () => void {
    this.warnIfUnattached()
    this.assertTopic(topic)
    const set = this.handlers.get(topic) ?? new Set<SubscriptionHandler>()
    set.add(handler)
    this.handlers.set(topic, set)
    let cancelled = false
    const cancel = () => {
      if (cancelled) {
        return
      }
      cancelled = true
      set.delete(handler)
      if (set.size === 0) {
        this.handlers.delete(topic)
      }
    }
    return this.resources.track(cancel, 'subscription')
  }

  /** 单次订阅（收到即取消） */
  once(topic: string, handler: SubscriptionHandler): () => void {
    let cancel: () => void = () => {}
    cancel = this.subscribe(topic, (payload) => {
      cancel()
      handler(payload)
    })
    return cancel
  }

  /** 取消订阅（指定 topic 或全部） */
  unsubscribe(topic?: string): void {
    if (topic === undefined) {
      this.handlers.clear()
      return
    }
    this.handlers.delete(topic)
  }

  /** 本地发布（开发 / 占位 / 本地组件间通信；不代替后端事件） */
  publish(topic: string, payload?: unknown): void {
    const set = this.handlers.get(topic)
    if (!set) {
      return
    }
    for (const handler of [...set]) {
      try {
        handler(payload)
      } catch (error) {
        this.reportError(error, { scope: 'subscription.handler', topic })
      }
    }
  }

  /** 订阅状态判定 */
  has(topic: string): boolean {
    return this.handlers.has(topic)
  }

  /** 幂等释放：取消全部订阅（内部异步资源释放）并触发组件根 / 根系释放链 */
  override dispose(): void {
    this.handlers.clear()
    this.resources.dispose()
    super.dispose()
  }

  /** 机制挂接标记（由组件根装配点调用） */
  attachToComponent(): void {
    this.attached = true
    this.resources.attachToComponent()
  }

  /** 机制脱离（由组件根装配点调用；不取消订阅） */
  detachFromComponent(): void {
    this.attached = false
    this.resources.detachFromComponent()
  }

  /** 释放联动（组件根 `dispose()` 时调用：取消全部订阅） */
  releaseFromComponent(): void {
    this.dispose()
  }

  /** 事件名校验：不符点分小写时开发态告警，**不阻断**（占位与兼容期可用） */
  private assertTopic(topic: string): void {
    if (!this.topicPattern.test(topic)) {
      this.log('warn', `subscription: 事件名「${topic}」不符合点分小写口径（领域.动作）`)
    }
  }

  private warnIfUnattached(): void {
    warnUnattachedMechanism(this.mechanismKey, this.attached)
  }
}

/** 组合式返回值：与 `BaseSubscription` 的公开能力等价 */
export interface UseSubscriptionBaseReturn {
  readonly source: SubscriptionSource
  readonly topics: readonly string[]
  setSource: (source: SubscriptionSource) => void
  subscribe: (topic: string, handler: SubscriptionHandler) => () => void
  once: (topic: string, handler: SubscriptionHandler) => () => void
  unsubscribe: (topic?: string) => void
  publish: (topic: string, payload?: unknown) => void
  has: (topic: string) => boolean
  /** 装配入口：`mechanisms.attach(subscription.mechanism)` */
  readonly mechanism: MechanismLike
  dispose: () => void
}

/** 作用域实例：承载与订阅基类完全相同的能力 */
class ScopedSubscription extends BaseSubscription {}

/**
 * 获取订阅能力（组合轨）。
 *
 * 处于组件 / 副作用作用域内时随作用域释放自动 `dispose()`（取消全部订阅）。
 */
export function useSubscriptionBase(options: SubscriptionOptions = {}): UseSubscriptionBaseReturn {
  const instance = new ScopedSubscription(options)
  if (getCurrentScope()) {
    onScopeDispose(() => instance.dispose())
  }
  return {
    get source() {
      return instance.source
    },
    get topics() {
      return instance.topics
    },
    setSource: (source) => instance.setSource(source),
    subscribe: (topic, handler) => instance.subscribe(topic, handler),
    once: (topic, handler) => instance.once(topic, handler),
    unsubscribe: (topic) => instance.unsubscribe(topic),
    publish: (topic, payload) => instance.publish(topic, payload),
    has: (topic) => instance.has(topic),
    mechanism: instance,
    dispose: () => instance.dispose(),
  }
}
