/** 稳定序列化：对象键排序、Set/Map 确定序、BigInt 转字符串、Date 转 ISO（对拍/存档/日志用）。 */

function compareKeys(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

function normalize(value: unknown): unknown {
  if (typeof value === 'bigint') {
    return value.toString()
  }
  if (value === null || typeof value !== 'object') {
    return value
  }
  if (value instanceof Date) {
    return value.toISOString()
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalize(item))
  }
  if (value instanceof Set) {
    return [...value]
      .map((item) => normalize(item))
      .sort((a, b) => compareKeys(stableStringify(a), stableStringify(b)))
  }
  if (value instanceof Map) {
    const entries = [...value.entries()]
      .map(([key, item]) => [String(key), normalize(item)] as [string, unknown])
      .sort((a, b) => compareKeys(a[0], b[0]))
    return Object.fromEntries(entries)
  }
  const entries = Object.entries(value as Record<string, unknown>)
    .sort(([a], [b]) => compareKeys(a, b))
    .map(([key, item]) => [key, normalize(item)] as [string, unknown])
  return Object.fromEntries(entries)
}

export function stableStringify(value: unknown): string {
  return JSON.stringify(normalize(value))
}
