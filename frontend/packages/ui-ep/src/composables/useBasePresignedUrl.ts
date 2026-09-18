/** 预签名投影：把核心预签名能力基类 `BasePresignedUrl` 投影为组合式（获取 / 失效重取 / 降级）。 */

import { BasePresignedUrl, type PresignedResult } from '@bms/core'
import { ref, type Ref } from 'vue'

/** 具体预签名（可实例化）。 */
class PresignedUrlState extends BasePresignedUrl {}

/** `useBasePresignedUrl` 返回面。 */
export interface UseBasePresignedUrlResult {
  /** 预签名基类实例。 */
  presigned: BasePresignedUrl
  /** 当前 URL（响应式）。 */
  url: Ref<string | undefined>
  /** 过期时间戳（响应式）。 */
  expiresAt: Ref<number>
  /** 设置获取器（宿主注入）。 */
  setFetcher: (fetcher?: () => Promise<PresignedResult>) => void
  /** 获取可用 URL（有效复用 / 失效重取 / 未注入降级）。 */
  get: () => Promise<string | undefined>
  /** 清除缓存（失效重取）。 */
  refresh: () => void
  /** 是否已过期。 */
  isExpired: (now?: number) => boolean
}

/**
 * 使用预签名投影。
 *
 * @returns 预签名基类实例与响应式面。
 */
export function useBasePresignedUrl(): UseBasePresignedUrlResult {
  const presigned = new PresignedUrlState()
  const url = ref<string | undefined>(presigned.url)
  const expiresAt = ref(presigned.expiresAt)

  function sync(): void {
    url.value = presigned.url
    expiresAt.value = presigned.expiresAt
  }

  return {
    presigned,
    url,
    expiresAt,
    setFetcher: (fetcher) => {
      presigned.fetcher = fetcher
    },
    get: async () => {
      const next = await presigned.get()
      sync()
      return next
    },
    refresh: () => {
      presigned.refresh()
      sync()
    },
    isExpired: (now) => presigned.isExpired(now),
  }
}
