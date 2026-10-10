/** 水印投影：把核心水印能力基类 `BaseWatermark` 投影为组合式（用户 / 租户文本与开关）。 */
import { BaseWatermark } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体水印（可实例化，`setUser` / `setTenant` / `setEnabled` 触发更新通知）。 */
class WatermarkState extends BaseWatermark {
    setUser(text) {
        super.setUser(text);
        this.notifyLifecycle('update');
    }
    setTenant(text) {
        super.setTenant(text);
        this.notifyLifecycle('update');
    }
    /**
     * 设置启用开关。
     *
     * @param enabled 是否启用。
     */
    setEnabled(enabled) {
        this.enabled = enabled;
        this.notifyLifecycle('update');
    }
}
/**
 * 使用水印投影。
 *
 * @param options 初始用户 / 租户文本。
 * @returns 水印基类实例与响应式面。
 */
export function useBaseWatermark(options = {}) {
    const watermark = new WatermarkState();
    if (options.user) {
        watermark.setUser(options.user);
    }
    if (options.tenant) {
        watermark.setTenant(options.tenant);
    }
    const text = ref(watermark.text);
    const enabled = ref(watermark.enabled);
    const off = watermark.onLifecycle((event) => {
        if (event === 'update') {
            text.value = watermark.text;
            enabled.value = watermark.enabled;
        }
    });
    onScopeDispose(off);
    return {
        watermark,
        text,
        enabled,
        setUser: (value) => watermark.setUser(value),
        setTenant: (value) => watermark.setTenant(value),
        setEnabled: (value) => watermark.setEnabled(value),
    };
}
