/**
 * `@bms/vue`：BMS 前端 Vue 绑定入口（组合式投影，只做核心实例 ↔ Vue 响应式的薄适配）。
 */

export { useValue, type UseValueResult } from './bindings/useValue'
export { useAccess, type UseAccessResult } from './bindings/useAccess'
