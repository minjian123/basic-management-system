/**
 * 图片处理：尺寸探测与压缩（Worker 优先，能力缺失 / 加载失败降级主线程 / 原文件）。
 *
 * **浏览器 API 只在本工具出现**（`createImageBitmap` / `Image` / `canvas` / `OffscreenCanvas` / `URL`）；
 * 压缩决策复用核心 `domain/file.ts` 的 `decideImageCompress`（纯函数，件层据此调用本工具）。
 */

import {
  IMAGE_COMPRESS_MAX_EDGE,
  IMAGE_COMPRESS_QUALITY,
  decideImageCompress,
  type FileMeta,
  type ImageCompressDecision,
  type ImageCompressOptions,
} from '@bms/core'

export { decideImageCompress, type ImageCompressDecision, type ImageCompressOptions }

/** 压缩选项（件层可覆盖）。 */
export interface ImageCompressRequest {
  /** 最大边长（像素）。 */
  maxEdge?: number
  /** 编码质量（0 ~ 1）。 */
  quality?: number
}

/** 工作线程请求。 */
export interface ImageProcessWorkerRequest {
  /** 图片文件。 */
  file: unknown
  /** 最大边长（像素）。 */
  maxEdge: number
  /** 编码质量。 */
  quality: number
  /** 输出类型（缺省保持原类型）。 */
  mime?: string
}

/** 工作线程响应。 */
export interface ImageProcessWorkerResponse {
  /** 压缩产物。 */
  blob?: Blob
  /** 失败原因。 */
  error?: string
}

/** 图片解码等待上限（毫秒；超时按探测失败降级）。 */
const IMAGE_DECODE_TIMEOUT = 3000

/**
 * 超时包装（超时 / 失败返回 `undefined`）。
 *
 * @param task 异步任务。
 * @param ms 超时毫秒。
 * @returns 结果或 `undefined`。
 */
function withTimeout<T>(task: Promise<T>, ms: number = IMAGE_DECODE_TIMEOUT): Promise<T | undefined> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(undefined), ms)
    task
      .then((value) => {
        clearTimeout(timer)
        resolve(value)
      })
      .catch(() => {
        clearTimeout(timer)
        resolve(undefined)
      })
  })
}

/**
 * 探测图片尺寸（`createImageBitmap` 优先、`Image` 降级；失败 / 超时返回 `undefined`）。
 *
 * @param file 图片文件。
 * @returns 尺寸或 `undefined`。
 */
export async function readImageDimension(file: unknown): Promise<{ width: number; height: number } | undefined> {
  const blob = file as Blob | undefined
  if (blob === undefined || blob === null) {
    return undefined
  }
  if (typeof globalThis.createImageBitmap === 'function') {
    const size = await withTimeout(
      globalThis.createImageBitmap(blob).then((bitmap) => {
        const result = { width: bitmap.width, height: bitmap.height }
        bitmap.close?.()
        return result
      }),
    )
    if (size !== undefined) {
      return size
    }
  }
  if (typeof Image !== 'function' || typeof URL.createObjectURL !== 'function') {
    return undefined
  }
  return withTimeout(
    new Promise<{ width: number; height: number } | undefined>((resolve) => {
      const url = URL.createObjectURL(blob)
      const image = new Image()
      image.onload = () => {
        URL.revokeObjectURL(url)
        resolve({ width: image.naturalWidth, height: image.naturalHeight })
      }
      image.onerror = () => {
        URL.revokeObjectURL(url)
        resolve(undefined)
      }
      image.src = url
    }),
  )
}

/**
 * 压缩图片（Worker 优先；能力缺失 / 失败返回原文件，不阻断上传）。
 *
 * @param file 图片文件。
 * @param options 压缩选项。
 * @returns 压缩产物或原文件。
 */
export async function compressImage(file: unknown, options: ImageCompressRequest = {}): Promise<unknown> {
  const blob = file as Blob | undefined
  if (blob === undefined || blob === null || typeof blob.slice !== 'function') {
    return file
  }
  const maxEdge = options.maxEdge ?? IMAGE_COMPRESS_MAX_EDGE
  const quality = options.quality ?? IMAGE_COMPRESS_QUALITY
  if (typeof Worker === 'function') {
    const result = await compressInWorker(blob, maxEdge, quality)
    if (result !== undefined) {
      return result
    }
  }
  return compressInMainThread(blob, maxEdge, quality)
}

/**
 * 决定是否压缩（复用核心决策，附能力可用性判断）。
 *
 * @param meta 文件元信息。
 * @param options 决策选项。
 * @returns 决策结果。
 */
export function planImageCompress(meta: FileMeta, options: ImageCompressOptions = {}): ImageCompressDecision {
  return decideImageCompress(meta, options)
}

/**
 * 创建对象 URL（本地预览；能力缺失返回 `undefined`）。
 *
 * @param source 文件 / Blob。
 * @returns 对象 URL 或 `undefined`。
 */
export function createObjectUrl(source: unknown): string | undefined {
  if (typeof URL.createObjectURL !== 'function') {
    return undefined
  }
  const blob = source as Blob | undefined
  if (blob === undefined || blob === null) {
    return undefined
  }
  try {
    return URL.createObjectURL(blob)
  } catch {
    return undefined
  }
}

/**
 * 释放对象 URL（幂等；能力缺失不报错）。
 *
 * @param url 对象 URL。
 */
export function revokeObjectUrl(url: string | undefined): void {
  if (url !== undefined && url !== '' && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(url)
  }
}

/**
 * Worker 压缩（不可用 / 失败返回 `undefined`）。
 *
 * @param blob 图片文件。
 * @param maxEdge 最大边长。
 * @param quality 编码质量。
 * @returns 压缩产物或 `undefined`。
 */
async function compressInWorker(blob: Blob, maxEdge: number, quality: number): Promise<Blob | undefined> {
  let worker: Worker | undefined
  try {
    worker = new Worker(new URL('./imageProcess.worker.ts', import.meta.url), { type: 'module' })
    return await new Promise<Blob | undefined>((resolve) => {
      worker?.addEventListener('message', (event: MessageEvent<ImageProcessWorkerResponse>) => {
        resolve(event.data.error === undefined ? event.data.blob : undefined)
      })
      worker?.addEventListener('error', () => resolve(undefined))
      worker?.postMessage({
        file: blob,
        maxEdge,
        quality,
        mime: blob.type === '' ? undefined : blob.type,
      } satisfies ImageProcessWorkerRequest)
    })
  } catch {
    return undefined
  } finally {
    worker?.terminate()
  }
}

/**
 * 主线程压缩（canvas 能力缺失返回原文件）。
 *
 * @param blob 图片文件。
 * @param maxEdge 最大边长。
 * @param quality 编码质量。
 * @returns 压缩产物或原文件。
 */
async function compressInMainThread(blob: Blob, maxEdge: number, quality: number): Promise<unknown> {
  const dimension = await readImageDimension(blob)
  if (dimension === undefined || typeof document === 'undefined') {
    return blob
  }
  const scale = Math.min(1, maxEdge / Math.max(dimension.width, dimension.height))
  const width = Math.max(1, Math.round(dimension.width * scale))
  const height = Math.max(1, Math.round(dimension.height * scale))
  const bitmap = await globalThis.createImageBitmap?.(blob)
  if (bitmap === undefined) {
    return blob
  }
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (context === null) {
    bitmap.close?.()
    return blob
  }
  context.drawImage(bitmap, 0, 0, width, height)
  bitmap.close?.()
  const type = blob.type === 'image/png' ? 'image/png' : 'image/jpeg'
  return new Promise<Blob>((resolve) => {
    canvas.toBlob(
      (result) => resolve(result ?? blob),
      type,
      type === 'image/png' ? undefined : quality,
    )
  })
}
