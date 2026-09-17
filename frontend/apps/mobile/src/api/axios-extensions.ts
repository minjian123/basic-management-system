/**
 * Axios 类型扩展：`metadata`（请求元数据：`silent` / `startedAt` / `skipAuthRefresh`）
 * 与内部重放标记（`__authRetried`）。
 */

export {}

declare module 'axios' {
  interface AxiosRequestConfig {
    /** 请求元数据（`silent` 跳过统一提示；`skipAuthRefresh` 跳过 401 刷新；`startedAt` 耗时统计） */
    metadata?: Record<string, unknown>
  }

  interface InternalAxiosRequestConfig {
    /** 401 已重放标记（每请求最多重放一次，防循环） */
    __authRetried?: boolean
  }
}
