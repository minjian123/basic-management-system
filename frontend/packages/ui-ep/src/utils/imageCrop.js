/**
 * 图片裁剪装配：cropperjs v2（Web Components，JS API 装配）懒加载单一落点。
 *
 * 装配失败（加载失败 / 能力缺失）返回 `undefined`，件层提示并降级直传原图；
 * 输出经选择区 `$toCanvas` 转为 PNG Blob（头像圆形以选择区圆形遮罩呈现，输出方形供件层圆形展示）。
 */
import { IMAGE_CROP_ASPECT, IMAGE_CROP_OUTPUT_MAX_EDGE } from '@bms/core';
/**
 * 在容器内装配裁剪器（cropperjs v2 懒加载；装配失败返回 `undefined`）。
 *
 * @param container 容器元素。
 * @param source 图片来源（`Blob` 兼容）。
 * @param options 装配选项。
 * @returns 裁剪控制面；不可用返回 `undefined`。
 */
export async function mountImageCropper(container, source, options = {}) {
    const blob = source;
    if (typeof document === 'undefined' || typeof URL.createObjectURL !== 'function' || blob === undefined || blob === null) {
        return undefined;
    }
    try {
        const { CropperCanvas, CropperImage, CropperSelection } = await import('cropperjs');
        const url = URL.createObjectURL(blob);
        const canvas = new CropperCanvas();
        canvas.background = false;
        const image = new CropperImage();
        image.setAttribute('src', url);
        const selection = new CropperSelection();
        selection.aspectRatio = options.aspect !== undefined && options.aspect > 0 ? options.aspect : IMAGE_CROP_ASPECT;
        selection.initialCoverage = 0.9;
        selection.movable = true;
        selection.resizable = true;
        selection.zoomable = true;
        if (options.shape === 'circle') {
            selection.style.borderRadius = '50%';
        }
        canvas.append(image, selection);
        container.replaceChildren(canvas);
        await image.$ready().catch(() => undefined);
        const maxEdge = options.outputMaxEdge ?? IMAGE_CROP_OUTPUT_MAX_EDGE;
        return {
            reset: () => {
                selection.$reset();
                image.$resetTransform();
            },
            zoom: (delta) => {
                image.$zoom(delta >= 0 ? 1.1 : 0.9);
            },
            toBlob: async () => {
                const aspect = selection.aspectRatio > 0 ? selection.aspectRatio : 1;
                const width = aspect >= 1 ? maxEdge : Math.max(1, Math.round(maxEdge * aspect));
                const height = aspect >= 1 ? Math.max(1, Math.round(maxEdge / aspect)) : maxEdge;
                const element = await selection.$toCanvas({ width, height });
                return await new Promise((resolve) => {
                    element.toBlob((result) => resolve(result ?? undefined), 'image/png');
                });
            },
            destroy: () => {
                canvas.remove();
                URL.revokeObjectURL(url);
            },
        };
    }
    catch {
        return undefined;
    }
}
