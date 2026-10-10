/**
 * 领域纯函数：虚拟列表可视区计算（定高快路径 + 动态高度累计偏移），与框架无关。
 */
/** 缺省缓冲条数。 */
const DEFAULT_BUFFER = 4;
/** 动态高度缺省估算值。 */
const DEFAULT_ESTIMATED = 44;
/**
 * 数值夹取。
 *
 * @param value 值。
 * @param min 下界。
 * @param max 上界。
 */
function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}
/**
 * 计算虚拟列表可视区。
 *
 * @param options 选项。
 * @returns 可视区起止索引、顶偏移与总高度。
 */
export function computeVirtualRange(options) {
    const count = Math.max(0, Math.floor(options.count));
    if (count === 0) {
        return { start: 0, end: 0, offsetTop: 0, totalHeight: 0 };
    }
    const buffer = Math.max(0, Math.floor(options.buffer ?? DEFAULT_BUFFER));
    const itemHeight = options.itemHeight !== undefined && options.itemHeight > 0 ? options.itemHeight : undefined;
    if (itemHeight !== undefined) {
        const totalHeight = count * itemHeight;
        const scrollTop = clamp(options.scrollTop, 0, totalHeight);
        const start = clamp(Math.floor(scrollTop / itemHeight) - buffer, 0, count - 1);
        const end = clamp(Math.ceil((scrollTop + options.viewportHeight) / itemHeight) + buffer, start + 1, count);
        return { start, end, offsetTop: start * itemHeight, totalHeight };
    }
    const estimated = options.offsets === undefined ? DEFAULT_ESTIMATED : undefined;
    const offsets = options.offsets ??
        Array.from({ length: count + 1 }, (_, index) => index * estimated);
    if (offsets.length < count + 1) {
        return computeVirtualRange({ ...options, itemHeight: estimated ?? DEFAULT_ESTIMATED });
    }
    const totalHeight = offsets[count] ?? 0;
    const scrollTop = clamp(options.scrollTop, 0, totalHeight);
    const viewportBottom = scrollTop + options.viewportHeight;
    let start = 0;
    let low = 0;
    let high = count - 1;
    while (low <= high) {
        const mid = (low + high) >> 1;
        if ((offsets[mid + 1] ?? totalHeight) <= scrollTop) {
            low = mid + 1;
        }
        else {
            start = mid;
            high = mid - 1;
        }
    }
    let end = count;
    for (let index = start; index < count; index += 1) {
        if ((offsets[index] ?? totalHeight) >= viewportBottom) {
            end = index;
            break;
        }
    }
    start = clamp(start - buffer, 0, count - 1);
    end = clamp(end + buffer, start + 1, count);
    return { start, end, offsetTop: offsets[start] ?? 0, totalHeight };
}
