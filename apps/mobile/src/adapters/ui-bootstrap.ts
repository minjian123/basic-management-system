/**
 * 移动端宿主装配（S4c 切流）：ui-vant 注入点接线。
 *
 * 权限判定：`configurePermissionChecker` ← 权限应用态 store（任意 / 全量语义）；
 * 确认对话框：ui-vant 自带 Vant 默认实现（无需宿主接线）。
 *
 * 在 `app.use(createPinia())` 之后调用（store 经闭包懒取，确保运行期有激活 pinia）。
 */

import { configurePermissionChecker } from '@bms/ui-vant'

import { usePermissionStore } from '@/stores/permission'

export function bootstrapUiBridge(): void {
  configurePermissionChecker((codes, mode) => {
    const store = usePermissionStore()
    return mode === 'all' ? store.hasAll([...codes]) : store.hasAny([...codes])
  })
}
