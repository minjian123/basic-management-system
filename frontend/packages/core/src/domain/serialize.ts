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

/** 十进制整数文本（字典条目 id 的提交形态）。 */
const INTEGER_TEXT_PATTERN = /^\d+$/

/**
 * 整数 id 序列化豁免：把指定路径上的字符串 id 写成**裸数字字面量**。
 *
 * 雪花 ID（63 位）超出 JS 安全整数，`Number(id)` 会丢精度；本函数不经过数字转换，
 * 直接把十进制文本写入 JSON，后端按整数解析即精确无损。
 *
 * 路径语法：点分隔层级，`*` 匹配任意键（数组自动展开到元素）；如 `data.region_id`、
 * `details.*.item_id`。命中路径的值为：
 * - 纯十进制字符串 → 裸字面量；空串 → `null`；
 * - 安全整数 → 原样输出；非安全整数 / 其它类型 → 抛错（不静默降级为字符串）。
 *
 * @param payload 提交载荷。
 * @param paths 整数 id 字段路径清单（见 `collectDictIdPaths`）。
 * @returns JSON 文本。
 */
export function stringifyIntegerIds(payload: unknown, paths: readonly string[]): string {
  const patterns = paths.map((path) => path.split('.').filter((segment) => segment !== ''))
  return serializeWithIntegerIds(payload, [], patterns)
}

/**
 * 递归序列化（命中路径输出整数裸字面量）。
 *
 * @param value 当前值。
 * @param trail 当前路径段。
 * @param patterns 命中路径模式。
 * @returns JSON 片段。
 */
function serializeWithIntegerIds(value: unknown, trail: readonly string[], patterns: readonly (readonly string[])[]): string {
  if (patterns.some((pattern) => matchIntegerPath(pattern, trail))) {
    return renderIntegerLiteral(value, trail)
  }
  if (value === null || value === undefined) {
    return 'null'
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => serializeWithIntegerIds(item, trail, patterns)).join(',')}]`
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const parts: string[] = []
    for (const [key, item] of Object.entries(record)) {
      if (item === undefined) {
        continue
      }
      parts.push(`${JSON.stringify(key)}:${serializeWithIntegerIds(item, [...trail, key], patterns)}`)
    }
    return `{${parts.join(',')}}`
  }
  return JSON.stringify(value) ?? 'null'
}

/**
 * 路径是否命中（`*` 匹配任意单段）。
 *
 * @param pattern 路径模式。
 * @param trail 当前路径。
 */
function matchIntegerPath(pattern: readonly string[], trail: readonly string[]): boolean {
  if (pattern.length !== trail.length) {
    return false
  }
  return pattern.every((segment, index) => segment === '*' || segment === trail[index])
}

/**
 * 渲染整数 id 字面量（数组逐项处理；非法值抛错）。
 *
 * @param value 当前值。
 * @param trail 当前路径（错误文案用）。
 * @returns JSON 片段。
 */
function renderIntegerLiteral(value: unknown, trail: readonly string[]): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => renderIntegerLiteral(item, trail)).join(',')}]`
  }
  if (value === null || value === undefined || value === '') {
    return 'null'
  }
  if (typeof value === 'string' && INTEGER_TEXT_PATTERN.test(value)) {
    return value
  }
  if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0) {
    return String(value)
  }
  throw new Error(`字典字段 ${trail.join('.')} 的条目 id 非法：${String(value)}`)
}
