/**
 * 容器组件类 · 通用容器共享类型（滚动容器起步，后续容器件复用）。
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
