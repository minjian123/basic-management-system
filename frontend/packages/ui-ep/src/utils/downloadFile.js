/** 浏览器下载触发（件层 DOM 语义的唯一落点，与 `utils/printWindow.ts` 同口径；核心与投影层不触 DOM）。 */
/**
 * 触发浏览器下载（blob 优先，其次 URL；两者皆无时不动作）。
 *
 * @param input 下载触发入参。
 */
export function triggerDownload(input) {
    if (typeof document === 'undefined' || typeof URL === 'undefined') {
        return;
    }
    const anchor = document.createElement('a');
    const blob = input.blob;
    let objectUrl = '';
    if (blob instanceof Blob) {
        objectUrl = URL.createObjectURL(blob);
        anchor.href = objectUrl;
    }
    else if (input.url !== undefined && input.url !== '') {
        anchor.href = input.url;
    }
    else {
        return;
    }
    anchor.download = input.filename;
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    if (objectUrl !== '') {
        URL.revokeObjectURL(objectUrl);
    }
}
