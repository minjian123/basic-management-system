/**
 * 关键词高亮与检索片段清洗单一落点：客户端关键词高亮（先转义再包裹 `<em>`）与
 * 后端返回高亮片段的**白名单清洗**（复用富文本净化口径，防 XSS）。
 *
 * 件层只消费本工具结果，不在组件内拼装 HTML。
 */

import { sanitizeHtml } from './sanitizeHtml'
import type { SearchHit } from '@bms/core'

/**
 * 转义纯文本中的 HTML 特殊字符。
 *
 * @param text 原文。
 * @returns 转义后文本。
 */
export function escapeSearchText(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 转义正则特殊字符。
 *
 * @param text 原文。
 * @returns 转义后文本。
 */
function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 关键词高亮（文本与关键词均先转义，命中以 `<em>` 包裹）。
 *
 * @param text 原文。
 * @param keyword 关键词（空串原样转义返回）。
 * @returns 高亮 HTML。
 */
export function highlightKeyword(text: string, keyword: string): string {
  const escaped = escapeSearchText(text)
  const trimmed = keyword.trim()
  if (trimmed === '') {
    return escaped
  }
  const pattern = new RegExp(`(${escapeRegExp(escapeSearchText(trimmed))})`, 'gi')
  return escaped.replace(pattern, '<em>$1</em>')
}

/**
 * 清洗检索返回的高亮片段（白名单，仅保留安全标签如 `<em>`）。
 *
 * @param html 原始片段。
 * @returns 清洗后 HTML。
 */
export function sanitizeHighlight(html: string): string {
  return sanitizeHtml(html)
}

/**
 * 标题是否含标记（后端已返回高亮）。
 *
 * @param text 标题。
 * @returns 是否含标记。
 */
function hasMarkup(text: string): boolean {
  return /<[a-z][\s\S]*>/i.test(text)
}

/**
 * 组装命中的标题与摘要高亮 HTML（片段优先清洗，标题未带标记时按关键词高亮）。
 *
 * @param hit 命中项。
 * @param keyword 关键词。
 * @returns 标题与摘要的 HTML。
 */
export function highlightHit(hit: SearchHit, keyword: string): { title: string; summary: string } {
  const title = hasMarkup(hit.title) ? sanitizeHighlight(hit.title) : highlightKeyword(hit.title, keyword)
  const summary = hit.highlight !== undefined ? sanitizeHighlight(hit.highlight) : ''
  return { title, summary }
}
