/** 水印投影：把核心水印能力基类 `BaseWatermark` 投影为组合式（用户 / 租户文本与开关）。 */

import { BaseWatermark } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体水印（可实例化，`setUser` / `setTenant` / `setEnabled` 触发更新通知）。 */
class WatermarkState extends BaseWatermark {
  override setUser(text: string): void {
    super.setUser(text)
    this.notifyLifecycle('update')
  }

  override setTenant(text: string): void {
    super.setTenant(text)
    this.notifyLifecycle('update')
  }

  /**
   * 设置启用开关。
   *
   * @param enabled 是否启用。
   */
  setEnabled(enabled: boolean): void {
    this.enabled = enabled
    this.notifyLifecycle('update')
  }
}

/** `useBaseWatermark` 返回面。 */
export interface UseBaseWatermarkResult {
  /** 水印基类实例。 */
  watermark: BaseWatermark
  /** 水印文本（用户 / 租户拼接，响应式）。 */
  text: Ref<string>
  /** 是否启用（响应式）。 */
  enabled: Ref<boolean>
  /** 设置用户信息。 */
  setUser: (text: string) => void
  /** 设置租户信息。 */
  setTenant: (text: string) => void
  /** 设置启用开关。 */
  setEnabled: (enabled: boolean) => void
}

/**
 * 使用水印投影。
 *
 * @param options 初始用户 / 租户文本。
 * @returns 水印基类实例与响应式面。
 */
export function useBaseWatermark(options: { user?: string; tenant?: string } = {}): UseBaseWatermarkResult {
  const watermark = new WatermarkState()
  if (options.user) {
    watermark.setUser(options.user)
  }
  if (options.tenant) {
    watermark.setTenant(options.tenant)
  }

  const text = ref(watermark.text)
  const enabled = ref(watermark.enabled)

  const off = watermark.onLifecycle((event) => {
    if (event === 'update') {
      text.value = watermark.text
      enabled.value = watermark.enabled
    }
  })
  onScopeDispose(off)

  return {
    watermark,
    text,
    enabled,
    setUser: (value) => watermark.setUser(value),
    setTenant: (value) => watermark.setTenant(value),
    setEnabled: (value) => watermark.setEnabled(value),
  }
}
