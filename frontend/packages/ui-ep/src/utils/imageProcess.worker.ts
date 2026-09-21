/**
 * 图片处理工作线程：按最大边长缩放并重编码（输出保持原类型，PNG 不降质）。
 *
 * 消息协议见 `utils/imageProcess.ts`（`ImageProcessWorkerRequest` / `ImageProcessWorkerResponse`）。
 */

import { IMAGE_COMPRESS_MAX_EDGE, IMAGE_COMPRESS_QUALITY } from '@bms/core'

import type { ImageProcessWorkerRequest, ImageProcessWorkerResponse } from './imageProcess'

/** 工作线程作用域（最小面，避免引入 webworker 类型库）。 */
const scope = self as unknown as {
  onmessage: ((event: MessageEvent<ImageProcessWorkerRequest>) => void) | null
  postMessage(message: ImageProcessWorkerResponse): void
}

/**
 * 压缩并回传。
 *
 * @param request 请求（文件与压缩参数）。
 */
async function run(request: ImageProcessWorkerRequest): Promise<void> {
  try {
    if (typeof OffscreenCanvas !== 'function' || typeof createImageBitmap !== 'function') {
      scope.postMessage({ error: '工作线程不支持图片处理' })
      return
    }
    const bitmap = await createImageBitmap(request.file as Blob)
    const maxEdge = request.maxEdge > 0 ? request.maxEdge : IMAGE_COMPRESS_MAX_EDGE
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
    const width = Math.max(1, Math.round(bitmap.width * scale))
    const height = Math.max(1, Math.round(bitmap.height * scale))
    const canvas = new OffscreenCanvas(width, height)
    const context = canvas.getContext('2d')
    if (context === null) {
      scope.postMessage({ error: '无法获取画布上下文' })
      return
    }
    context.drawImage(bitmap, 0, 0, width, height)
    bitmap.close()
    const type = request.mime === 'image/png' || request.mime === undefined ? request.mime ?? 'image/jpeg' : 'image/jpeg'
    const blob = await canvas.convertToBlob({
      type,
      quality: type === 'image/png' ? undefined : (request.quality > 0 ? request.quality : IMAGE_COMPRESS_QUALITY),
    })
    scope.postMessage({ blob })
  } catch (error) {
    scope.postMessage({ error: error instanceof Error ? error.message : '图片压缩失败' })
  }
}

scope.onmessage = (event) => {
  void run(event.data)
}
