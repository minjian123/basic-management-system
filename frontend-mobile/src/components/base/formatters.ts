/**
 * 名义格式化器注册表（片段层）：`useDisplayBase` 的 `formatter` 名称分发。
 *
 * - 内置：`amount` / `number` / `percent` / `date` / `datetime` / `boolean`；
 * - 扩展：业务 / 消费方经 `registerFormatter` 注册（重复注册覆盖；开发态经根系日志提示）；
 * - 未注册名称仍由 `useDisplayBase` 回退 `String(value)`（占位口径不变）。
 * 纯函数本体见 `src/utils/format.ts`（职责边界：本表只做「名称 → 调度」）。
 */

import { i18n } from '@/i18n'
import { formatAmount, formatDate, formatDateTime, formatNumber, formatPercent } from '@/utils/format'

/** 名义格式化器签名 */
export type ValueFormatter = (value: unknown, options?: { locale?: string; timezone?: string }) => string

function boolText(value: unknown): string {
  const key = value === true ? 'common.yes' : 'common.no'
  const fallback = value === true ? '是' : '否'
  const translate = i18n.global.t as unknown as (key: string) => string
  const text = translate(key)
  return text === key ? fallback : text
}

/** 内置格式化器（模块加载即注册） */
export const BUILTIN_FORMATTERS: Record<string, ValueFormatter> = {
  amount: (value, options) => formatAmount(value, options),
  number: (value, options) => formatNumber(value, options),
  percent: (value, options) => formatPercent(value, options),
  date: (value, options) => formatDate(value, options),
  datetime: (value, options) => formatDateTime(value, options),
  boolean: (value) => boolText(value),
}

const registry = new Map<string, ValueFormatter>()

function registerBuiltins(): void {
  for (const [name, formatter] of Object.entries(BUILTIN_FORMATTERS)) {
    registry.set(name, formatter)
  }
}

registerBuiltins()

/** 注册（扩展 / 覆盖）名义格式化器 */
export function registerFormatter(name: string, formatter: ValueFormatter): void {
  const key = name.trim()
  if (!key) {
    return
  }
  registry.set(key, formatter)
}

/** 解析名义格式化器（未注册返回 `undefined`） */
export function resolveFormatter(name: string): ValueFormatter | undefined {
  return registry.get(name.trim())
}

/** 复位为内置集（测试用） */
export function resetFormatters(): void {
  registry.clear()
  registerBuiltins()
}
