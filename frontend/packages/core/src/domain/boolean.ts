/**
 * 布尔域纯函数（框架无关核心）：开关 / 布尔字段 / 列表内联切换共用。
 *
 * 后端 `SMALLINT` 1/0 与布尔字面量统一归一为 `boolean | null`（前端只暴露布尔 / 空）；
 * `0` 与 `false` 不得被空值判定吞掉（`null` 是「未设置」，`false` 是「明确关闭」）。
 */

const TRUE_LITERALS = new Set(['1', 'true'])
const FALSE_LITERALS = new Set(['0', 'false'])

/** 归一布尔值（`true`/`1`/`'1'`/`'true'` → `true`；`false`/`0`/`'0'`/`'false'` → `false`；空与无法识别 → `null`） */
export function normalizeBooleanValue(value: unknown): boolean | null {
  if (value === true || value === false) {
    return value
  }
  if (typeof value === 'number') {
    if (value === 1) {
      return true
    }
    if (value === 0) {
      return false
    }
    return null
  }
  if (typeof value === 'string') {
    const text = value.trim().toLowerCase()
    if (TRUE_LITERALS.has(text)) {
      return true
    }
    if (FALSE_LITERALS.has(text)) {
      return false
    }
    return null
  }
  return null
}
