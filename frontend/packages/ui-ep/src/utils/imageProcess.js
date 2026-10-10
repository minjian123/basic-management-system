/**
 * 图片处理：尺寸探测与压缩（Worker 优先，能力缺失 / 加载失败降级主线程 / 原文件）。
 *
 * **浏览器 API 只在本工具出现**（`createImageBitmap` / `Image` / `canvas` / `OffscreenCanvas` / `URL`）；
 * 压缩决策复用核心 `domain/file.ts` 的 `decideImageCompress`（纯函数，件层据此调用本工具）。
 */
import { IMAGE_COMPRESS_MAX_EDGE, IMAGE_COMPRESS_QUALITY, decideImageCompress, } from '@bms/core';
export { decideImageCompress };
/** 图片解码等待上限（毫秒；超时按探测失败降级）。 */
const IMAGE_DECODE_TIMEOUT = 3000;
/**
 * 超时包装（超时 / 失败返回 `undefined`）。
 *
 * @param task 异步任务。
 * @param ms 超时毫秒。
 * @returns 结果或 `undefined`。
 */
function withTimeout(task, ms = IMAGE_DECODE_TIMEOUT) {
    return new Promise((resolve) => {
        const timer = setTimeout(() => resolve(undefined), ms);
        task
            .then((value) => {
            clearTimeout(timer);
            resolve(value);
        })
            .catch(() => {
            clearTimeout(timer);
            resolve(undefined);
        });
    });
}
/**
 * 探测图片尺寸（`createImageBitmap` 优先、`Image` 降级；失败 / 超时返回 `undefined`）。
 *
 * @param file 图片文件。
 * @returns 尺寸或 `undefined`。
 */
export async function readImageDimension(file) {
    const blob = file;
    if (blob === undefined || blob === null) {
        return undefined;
    }
    if (typeof globalThis.createImageBitmap === 'function') {
        const size = await withTimeout(globalThis.createImageBitmap(blob).then((bitmap) => {
            const result = { width: bitmap.width, height: bitmap.height };
            bitmap.close?.();
            return result;
        }));
        if (size !== undefined) {
            return size;
        }
    }
    if (typeof Image !== 'function' || typeof URL.createObjectURL !== 'function') {
        return undefined;
    }
    return withTimeout(new Promise((resolve) => {
        const url = URL.createObjectURL(blob);
        const image = new Image();
        image.onload = () => {
            URL.revokeObjectURL(url);
            resolve({ width: image.naturalWidth, height: image.naturalHeight });
        };
        image.onerror = () => {
            URL.revokeObjectURL(url);
            resolve(undefined);
        };
        image.src = url;
    }));
}
/**
 * 压缩图片（Worker 优先；能力缺失 / 失败返回原文件，不阻断上传）。
 *
 * @param file 图片文件。
 * @param options 压缩选项。
 * @returns 压缩产物或原文件。
 */
export async function compressImage(file, options = {}) {
    const blob = file;
    if (blob === undefined || blob === null || typeof blob.slice !== 'function') {
        return file;
    }
    const maxEdge = options.maxEdge ?? IMAGE_COMPRESS_MAX_EDGE;
    const quality = options.quality ?? IMAGE_COMPRESS_QUALITY;
    if (typeof Worker === 'function') {
        const result = await compressInWorker(blob, maxEdge, quality);
        if (result !== undefined) {
            return result;
        }
    }
    return compressInMainThread(blob, maxEdge, quality);
}
/**
 * 决定是否压缩（复用核心决策，附能力可用性判断）。
 *
 * @param meta 文件元信息。
 * @param options 决策选项。
 * @returns 决策结果。
 */
export function planImageCompress(meta, options = {}) {
    return decideImageCompress(meta, options);
}
/**
 * 创建对象 URL（本地预览；能力缺失返回 `undefined`）。
 *
 * @param source 文件 / Blob。
 * @returns 对象 URL 或 `undefined`。
 */
export function createObjectUrl(source) {
    if (typeof URL.createObjectURL !== 'function') {
        return undefined;
    }
    const blob = source;
    if (blob === undefined || blob === null) {
        return undefined;
    }
    try {
        return URL.createObjectURL(blob);
    }
    catch {
        return undefined;
    }
}
/**
 * 释放对象 URL（幂等；能力缺失不报错）。
 *
 * @param url 对象 URL。
 */
export function revokeObjectUrl(url) {
    if (url !== undefined && url !== '' && typeof URL.revokeObjectURL === 'function') {
        URL.revokeObjectURL(url);
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
async function compressInWorker(blob, maxEdge, quality) {
    let worker;
    try {
        worker = new Worker(new URL('./imageProcess.worker.ts', import.meta.url), { type: 'module' });
        return await new Promise((resolve) => {
            worker?.addEventListener('message', (event) => {
                resolve(event.data.error === undefined ? event.data.blob : undefined);
            });
            worker?.addEventListener('error', () => resolve(undefined));
            worker?.postMessage({
                file: blob,
                maxEdge,
                quality,
                mime: blob.type === '' ? undefined : blob.type,
            });
        });
    }
    catch {
        return undefined;
    }
    finally {
        worker?.terminate();
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
async function compressInMainThread(blob, maxEdge, quality) {
    const dimension = await readImageDimension(blob);
    if (dimension === undefined || typeof document === 'undefined') {
        return blob;
    }
    const scale = Math.min(1, maxEdge / Math.max(dimension.width, dimension.height));
    const width = Math.max(1, Math.round(dimension.width * scale));
    const height = Math.max(1, Math.round(dimension.height * scale));
    const bitmap = await globalThis.createImageBitmap?.(blob);
    if (bitmap === undefined) {
        return blob;
    }
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (context === null) {
        bitmap.close?.();
        return blob;
    }
    context.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();
    const type = blob.type === 'image/png' ? 'image/png' : 'image/jpeg';
    return new Promise((resolve) => {
        canvas.toBlob((result) => resolve(result ?? blob), type, type === 'image/png' ? undefined : quality);
    });
}
