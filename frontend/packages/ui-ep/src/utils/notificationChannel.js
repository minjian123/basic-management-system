/** 通知多标签同步工具（`BroadcastChannel` 单一落点；能力缺失静默降级）。 */
/**
 * 创建多标签同步通道（无 `BroadcastChannel` 能力时回落空实现）。
 *
 * @param name 通道名。
 * @param handler 收到远端消息的回调。
 * @returns 通道句柄。
 */
export function createNotificationChannel(name, handler) {
    if (typeof BroadcastChannel === 'undefined') {
        return { publish: () => { }, close: () => { } };
    }
    const channel = new BroadcastChannel(name);
    channel.onmessage = (event) => {
        if (event.data !== null && typeof event.data === 'object') {
            handler(event.data);
        }
    };
    return {
        publish: (message) => {
            channel.postMessage(message);
        },
        close: () => {
            channel.close();
        },
    };
}
