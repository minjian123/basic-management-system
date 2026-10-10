/**
 * 文件哈希：整文件 + 每片 SHA-256（Worker 优先，能力缺失 / 加载失败降级主线程）。
 *
 * **浏览器 API 只在本工具出现**（`Blob` / `Worker`）；核心 `domain/file.ts` 提供纯 TS 增量实现。
 */
import { FILE_PART_SIZE, createSha256 } from '@bms/core';
/**
 * 主线程计算整文件与每片哈希。
 *
 * @param blob 文件对象。
 * @param partSize 分片大小（字节）。
 * @param signal 中断信号（可选）。
 * @returns 哈希结果（中断返回空结果）。
 */
async function hashInMainThread(blob, partSize, signal) {
    const whole = createSha256();
    const partHashes = [];
    let offset = 0;
    while (offset < blob.size) {
        if (signal?.aborted === true) {
            return { sha256: '', partHashes: [] };
        }
        const end = Math.min(offset + partSize, blob.size);
        const chunk = new Uint8Array(await blob.slice(offset, end).arrayBuffer());
        whole.update(chunk);
        const part = createSha256();
        part.update(chunk);
        partHashes.push(part.digestToHex());
        offset = end;
    }
    if (blob.size === 0) {
        return { sha256: whole.digestToHex(), partHashes: [] };
    }
    return { sha256: whole.digestToHex(), partHashes };
}
/**
 * 计算整文件与每片 SHA-256（Worker 优先；不可用环境降级主线程）。
 *
 * @param file 文件对象（`Blob` 兼容）。
 * @param options 选项（分片大小 / 中断信号）。
 * @returns 哈希结果；文件对象不可用返回空结果。
 */
export async function hashFile(file, options = {}) {
    const blob = file;
    if (blob === undefined || blob === null || typeof blob.slice !== 'function' || typeof blob.size !== 'number') {
        return { sha256: '', partHashes: [] };
    }
    const partSize = options.partSize !== undefined && options.partSize > 0 ? options.partSize : FILE_PART_SIZE;
    if (typeof Worker === 'function') {
        const result = await hashInWorker(blob, partSize);
        if (result !== undefined) {
            return result;
        }
    }
    return hashInMainThread(blob, partSize, options.signal);
}
/**
 * Worker 计算哈希（不可用 / 失败返回 `undefined`）。
 *
 * @param blob 文件对象。
 * @param partSize 分片大小。
 * @returns 哈希结果或 `undefined`。
 */
async function hashInWorker(blob, partSize) {
    let worker;
    try {
        worker = new Worker(new URL('./fileHash.worker.ts', import.meta.url), { type: 'module' });
        const result = await new Promise((resolve) => {
            worker?.addEventListener('message', (event) => {
                const data = event.data;
                if (data.error !== undefined || data.sha256 === undefined) {
                    resolve(undefined);
                    return;
                }
                resolve({ sha256: data.sha256, partHashes: data.partHashes ?? [] });
            });
            worker?.addEventListener('error', () => resolve(undefined));
            worker?.postMessage({ file: blob, partSize });
        });
        return result;
    }
    catch {
        return undefined;
    }
    finally {
        worker?.terminate();
    }
}
