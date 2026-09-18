/** 统一响应解包（`{ code, message, data }`）。 */

import type { ApiResponse, PageResponse } from '@bms/core'

import { ApiError } from './error'

/**
 * 解包统一响应（业务码非 0 抛 `ApiError`）。
 *
 * @param payload 统一响应。
 */
export function unwrap<T>(payload: ApiResponse<T>): T {
  if (payload.code !== 0) {
    throw new ApiError(payload.code, payload.message, { userMessage: payload.message })
  }
  return payload.data
}

/**
 * 解包分页响应。
 *
 * @param payload 统一响应（数据为分页结构）。
 */
export function unwrapPage<T>(payload: ApiResponse<PageResponse<T>>): PageResponse<T> {
  return unwrap(payload)
}
