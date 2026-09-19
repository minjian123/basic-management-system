/** 下载触发投影：把核心能力基类 `BaseFileDownload` 投影为组合式（取址 / 触发 / 失败重试）。 */

import {
  BaseFileDownload,
  type BasePresignedUrl,
  type DownloadFetcher,
  type DownloadPhase,
  type DownloadRequest,
  type DownloadResult,
  type DownloadTrigger,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体下载触发件（可实例化）。 */
class FileDownload extends BaseFileDownload {}

/** 选项。 */
export interface UseBaseFileDownloadOptions {
  /** 浏览器触发处理函数（件层注入；未注入即占位）。 */
  trigger?: DownloadTrigger
  /** 取址处理函数（宿主注入）。 */
  fetcher?: DownloadFetcher
  /** 预签名能力（取址回退）。 */
  presigned?: BasePresignedUrl
}

/** `useBaseFileDownload` 返回面。 */
export interface UseBaseFileDownloadResult {
  /** 下载基类实例。 */
  download: BaseFileDownload
  /** 下载阶段（响应式）。 */
  phase: Ref<DownloadPhase>
  /** 最近取到的 URL（响应式）。 */
  url: Ref<string>
  /** 最近使用的文件名（响应式）。 */
  filename: Ref<string>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 是否就绪（已注入触发手段，响应式）。 */
  ready: Ref<boolean>
  /** 是否下载中（响应式）。 */
  busy: Ref<boolean>
  /** 注入触发处理函数（件层默认注入 `triggerDownload`）。 */
  setTrigger: (trigger?: DownloadTrigger) => void
  /** 注入取址处理函数。 */
  setFetcher: (fetcher?: DownloadFetcher) => void
  /** 执行下载。 */
  run: (input?: DownloadRequest) => Promise<DownloadResult | undefined>
  /** 重试上次失败下载。 */
  retry: () => Promise<DownloadResult | undefined>
  /** 复位（保留注入的触发与取址）。 */
  reset: () => void
}

/**
 * 使用下载触发投影。
 *
 * @param options 选项。
 * @returns 下载基类实例与响应式面。
 */
export function useBaseFileDownload(options: UseBaseFileDownloadOptions = {}): UseBaseFileDownloadResult {
  const download = new FileDownload()
  if (options.trigger !== undefined) {
    download.trigger = options.trigger
  }
  if (options.fetcher !== undefined) {
    download.fetcher = options.fetcher
  }
  if (options.presigned !== undefined) {
    download.presigned = markRaw(toRaw(options.presigned))
  }

  const phase = ref(download.phase)
  const url = ref(download.url)
  const filename = ref(download.filename)
  const errorMessage = ref(download.errorMessage)
  const ready = ref(download.ready)
  const busy = ref(download.busy)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    phase.value = download.phase
    url.value = download.url
    filename.value = download.filename
    errorMessage.value = download.errorMessage
    ready.value = download.ready
    busy.value = download.busy
  }

  const off = download.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    download,
    phase,
    url,
    filename,
    errorMessage,
    ready,
    busy,
    setTrigger: (trigger) => {
      download.trigger = trigger
      sync()
    },
    setFetcher: (fetcher) => {
      download.fetcher = fetcher
      sync()
    },
    run: async (input) => {
      const result = await download.download(input)
      sync()
      return result
    },
    retry: async () => {
      const result = await download.retry()
      sync()
      return result
    },
    reset: () => {
      download.reset()
      sync()
    },
  }
}
