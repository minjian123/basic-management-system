/** 富文本白名单清洗（前端 DOMPurify，白名单与后端一致口径）。 */

import DOMPurify from 'dompurify'

/** 允许的标签（与后端白名单保持一致口径）。 */
export const RICH_TEXT_ALLOWED_TAGS = [
  'p',
  'br',
  'strong',
  'em',
  'u',
  's',
  'ul',
  'ol',
  'li',
  'h1',
  'h2',
  'h3',
  'h4',
  'blockquote',
  'code',
  'pre',
  'a',
  'img',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'hr',
  'span',
] as const

/** 允许的属性。 */
export const RICH_TEXT_ALLOWED_ATTR = ['href', 'target', 'rel', 'src', 'alt', 'width', 'height', 'class'] as const

/**
 * 清洗富文本 HTML（去除脚本 / 事件属性 / 危险协议，仅保留白名单标签与属性）。
 *
 * @param html 原始 HTML。
 * @returns 清洗后的 HTML。
 */
export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [...RICH_TEXT_ALLOWED_TAGS],
    ALLOWED_ATTR: [...RICH_TEXT_ALLOWED_ATTR],
    FORBID_ATTR: ['style'],
    ALLOW_DATA_ATTR: false,
  })
}

/**
 * 取净化后的纯文本（用于字数统计 / 校验）。
 *
 * @param html HTML。
 * @returns 纯文本。
 */
export function sanitizeToText(html: string): string {
  const cleaned = sanitizeHtml(html)
  return cleaned
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .trim()
}
