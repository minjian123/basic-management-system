/**
 * 领域纯函数：稳定序列化（键排序，便于比对与缓存键）与内容派生散列。
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

/**
 * FNV-1a（32 位）字符串散列（内容派生幂等键用，不依赖加密库）。
 *
 * @param value 待散列文本。
 * @returns 8 位十六进制散列值。
 */
export function fnv1aHex(value: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}
