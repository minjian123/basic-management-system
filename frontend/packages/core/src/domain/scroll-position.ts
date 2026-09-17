/**
 * 滚动位置存储（框架无关核心领域层）：`ScrollContainer` 的 `keepPosition` 消费。
 *
 * - **内存适配器**（默认）：模块级单例，同一会话内跨挂载保持（进程级不落盘）；
 * - **`sessionStorage` 适配器**：环境不可用（隐私模式 / SSR）时自动回落内存适配器，读取不抛错；
 * - 存储键 = `positionKey`（缺省由组件以实例 uid 代键）。
 *
 * 本模块纯 TS（不依赖 DOM 类型：宿主存储以最小结构面探测 `globalThis`）。
 */

/** 滚动度量（`scroll` / `reach-bottom` / `reach-top` 事件载荷） */
export interface ScrollMetrics {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

/** 滚动位置存储适配器（Storage 兼容子集；可接 `sessionStorage` 等） */
export interface ScrollStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

/** 滚动位置存储（键 = `ScrollContainer` 的 `positionKey`，缺省为组件 uid） */
export interface ScrollPositionStore {
  get(key: string): number | undefined
  set(key: string, top: number): void
  remove(key: string): void
}

/** 内存适配器（Map 实现，进程内存活） */
export function createMemoryScrollStorage(): ScrollStorage {
  const map = new Map<string, string>()
  return {
    getItem: (key) => (map.has(key) ? (map.get(key) as string) : null),
    setItem: (key, value) => {
      map.set(key, value)
    },
    removeItem: (key) => {
      map.delete(key)
    },
  }
}

/** 默认适配器单例（组件模块共享；跨挂载保持） */
export const defaultScrollStorage: ScrollStorage = createMemoryScrollStorage()

/** 探测可用的 `sessionStorage`（隐私模式 / SSR 返回 `null`） */
function probeSessionStorage(prefix: string): ScrollStorage | null {
  try {
    const candidate = (globalThis as { sessionStorage?: ScrollStorage }).sessionStorage
    if (!candidate) {
      return null
    }
    candidate.setItem(`${prefix}__probe__`, '1')
    candidate.removeItem(`${prefix}__probe__`)
    return candidate
  } catch {
    return null
  }
}

/** `sessionStorage` 适配器（前缀默认 `bms:scroll:`；不可用时回落内存适配器） */
export function createSessionScrollStorage(prefix = 'bms:scroll:'): ScrollStorage {
  const target = probeSessionStorage(prefix)
  if (!target) {
    return createMemoryScrollStorage()
  }
  return {
    getItem: (key) => {
      try {
        return target.getItem(prefix + key)
      } catch {
        return null
      }
    },
    setItem: (key, value) => {
      try {
        target.setItem(prefix + key, value)
      } catch {
        // 静默丢弃（容量 / 权限）
      }
    },
    removeItem: (key) => {
      try {
        target.removeItem(prefix + key)
      } catch {
        // 静默
      }
    },
  }
}

/** 滚动位置存储工厂（缺省经默认内存适配器） */
export function createScrollPositionStore(
  storage: ScrollStorage = defaultScrollStorage,
): ScrollPositionStore {
  return {
    get: (key) => {
      const raw = storage.getItem(key)
      if (raw === null || raw === '') {
        return undefined
      }
      const value = Number(raw)
      return Number.isFinite(value) ? value : undefined
    },
    set: (key, top) => {
      if (!Number.isFinite(top)) {
        return
      }
      storage.setItem(key, String(Math.max(0, Math.round(top))))
    },
    remove: (key) => {
      storage.removeItem(key)
    },
  }
}
