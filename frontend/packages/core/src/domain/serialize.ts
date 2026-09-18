/**
 * 领域纯函数：稳定序列化（键排序，便于比对与缓存键）。
 */

/**
 * 稳定序列化：对象键按字典序排列；不可序列化值降级 `String(value)`。
 *
 * @param value 任意值。
 * @returns 稳定 JSON 字符串。
 */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value) ?? String(value)
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`
  }
  const record = value as Record<string, unknown>
  const keys = Object.keys(record).sort()
  return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(',')}}`
}
