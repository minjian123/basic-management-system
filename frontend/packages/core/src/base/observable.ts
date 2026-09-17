/**
 * 可订阅状态（框架无关核心）：核心能力的响应式基元。
 *
 * 纯 TS（无 Vue）——渲染插件（Vue 等）据此投影（如 `shallowRef` + `subscribe` → `triggerRef`）；
 * 核心状态机只依赖「读 / 写 / 订阅」三件事，保证任意引擎可桥接、可替换。
 */

export interface Observable<T> {
  get(): T
  /** 订阅变化（返回取消函数） */
  subscribe(listener: (value: T) => void): () => void
}

export interface MutableObservable<T> extends Observable<T> {
  set(value: T): void
}

export function observable<T>(initial: T): MutableObservable<T> {
  let current = initial
  const listeners = new Set<(value: T) => void>()
  return {
    get: () => current,
    set: (value: T) => {
      if (Object.is(current, value)) {
        return
      }
      current = value
      for (const listener of [...listeners]) {
        listener(current)
      }
    },
    subscribe: (listener) => {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
  }
}
