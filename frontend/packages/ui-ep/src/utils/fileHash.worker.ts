/**
 * 文件哈希工作线程：整文件 + 每片 SHA-256（同一遍读取同时产出）。
 *
 * 消息协议见 `utils/fileHash.ts`（`FileHashWorkerRequest` / `FileHashWorkerResponse`）；
 * 增量实现复用核心 `domain/file.ts` 的 `createSha256`。
 */

import { FILE_PART_SIZE, createSha256 } from '@bms/core'

import type { FileHashWorkerRequest, FileHashWorkerResponse } from './fileHash'

/** 工作线程作用域（最小面，避免引入 webworker 类型库）。 */
const scope = self as unknown as {
  onmessage: ((event: MessageEvent<FileHashWorkerRequest>) => void) | null
  postMessage(message: FileHashWorkerResponse): void
}

/**
 * 计算哈希并回传。
 *
 * @param request 请求（文件与分片大小）。
 */
async function run(request: FileHashWorkerRequest): Promise<void> {
  try {
    const blob = request.file as Blob
    const partSize = request.partSize > 0 ? request.partSize : FILE_PART_SIZE
    const whole = createSha256()
    const partHashes: string[] = []
    let offset = 0
    while (offset < blob.size) {
      const end = Math.min(offset + partSize, blob.size)
      const chunk = new Uint8Array(await blob.slice(offset, end).arrayBuffer())
      whole.update(chunk)
      const part = createSha256()
      part.update(chunk)
      partHashes.push(part.digestToHex())
      offset = end
    }
    scope.postMessage({ sha256: whole.digestToHex(), partHashes })
  } catch (error) {
    scope.postMessage({ error: error instanceof Error ? error.message : '哈希计算失败' })
  }
}

scope.onmessage = (event) => {
  void run(event.data)
}
