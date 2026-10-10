/** 防抖工具：定时器统一入口（远程搜索等场景由件层调用，组件不得自行调度定时器）。 */
/**
 * 创建防抖函数。
 *
 * @param fn 目标函数。
 * @param wait 等待毫秒数（负数按 0）。
 * @returns 防抖函数（含 `cancel`）。
 */
export function debounce(fn, wait) {
    let timer;
    const delay = Math.max(0, wait);
    const wrapped = (...args) => {
        if (timer !== undefined) {
            clearTimeout(timer);
        }
        timer = setTimeout(() => {
            timer = undefined;
            fn(...args);
        }, delay);
    };
    wrapped.cancel = () => {
        if (timer !== undefined) {
            clearTimeout(timer);
            timer = undefined;
        }
    };
    return wrapped;
}
