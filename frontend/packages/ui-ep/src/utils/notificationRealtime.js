/** 通知轮询占位与页面可见性工具（浏览器 API 单一落点；核心与投影判定逻辑不触 DOM）。 */
import { NOTIFICATION_POLL_INTERVAL } from '@bms/core';
import { onVisibilityChange } from './visibility';
export { onVisibilityChange };
/**
 * 启动未读数轮询占位（仅页面可见时触发；未注入实时适配器时使用）。
 *
 * @param options 选项。
 * @returns 启停句柄。
 */
export function startUnreadPolling(options) {
    const interval = Math.max(1, options.intervalMs ?? NOTIFICATION_POLL_INTERVAL);
    const timer = setInterval(() => {
        if (options.visible()) {
            void options.loadUnread();
        }
    }, interval);
    return {
        stop: () => clearInterval(timer),
        kick: () => {
            if (options.visible()) {
                void options.loadUnread();
            }
        },
    };
}
