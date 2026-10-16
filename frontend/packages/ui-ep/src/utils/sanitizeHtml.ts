/**
 * 富文本白名单清洗（前端 DOMPurify，白名单与后端一致口径）。
 *
 * **按消费场景分档**（2026-10-14 登记，前端组件库 11_03）：
 * - `strict`（缺省）：既有口径（`ALLOW_DATA_ATTR: false`、`style` 整属性禁用、无 `div` / `sub` / `sup`），
 *   供 `searchHighlight` / `aiMarkdown` / `IconRenderer` 等**非富文本**消费方使用——既有调用零影响；
 * - `richtext`：按《组件设计 · 富文本字段》§4 白名单放宽——补块级 `div`、行内 `sub` / `sup`，
 *   `style` 属性级白名单（仅 `text-align` / `text-indent` / `width` / `height` / `max-width`），
 *   **禁止 `data:` 图片**，放行附件卡片 `data-file-id` / `data-file-name` / `data-file-size`，
 *   `a` 强制 `rel="noopener noreferrer"`、`img` 强制 `referrerpolicy="no-referrer"`。
 */

import DOMPurify from 'dompurify'

/** 清洗档位。 */
export type SanitizeProfile = 'strict' | 'richtext'

/** 允许的标签（严格档；与后端白名单保持一致口径）。 */
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

/** 允许的属性（严格档）。 */
export const RICH_TEXT_ALLOWED_ATTR = ['href', 'target', 'rel', 'src', 'alt', 'width', 'height', 'class'] as const

/** 富文本档允许的标签（严格档 + `div` / `sub` / `sup`，对齐节点 §4 白名单）。 */
export const RICH_TEXT_ALLOWED_TAGS_PROFILE = [...RICH_TEXT_ALLOWED_TAGS, 'div', 'sub', 'sup'] as const

/** 富文本档允许的属性（严格档 + `style` + 附件卡片 `data-*`；`data-*` 显式列名、不放开全部）。 */
export const RICH_TEXT_ALLOWED_ATTR_PROFILE = [
  ...RICH_TEXT_ALLOWED_ATTR,
  'style',
  'referrerpolicy',
  'data-file-id',
  'data-file-name',
  'data-file-size',
] as const

/** `style` 属性级白名单（节点 §4：仅保留以下属性，其余剥离）。 */
export const RICH_TEXT_ALLOWED_STYLE_PROPS = ['text-align', 'text-indent', 'width', 'height', 'max-width'] as const

/** 禁止的图片协议（节点 §4：`img.src` 禁止 `data:` 与 `javascript:`）。 */
const FORBIDDEN_IMG_SCHEME = /^\s*(?:data|javascript|vbscript)\s*:/i

/** `style` 声明中的危险函数（节点 §4：禁 `expression()`、禁 `url(...)`）。 */
const DANGEROUS_STYLE_VALUE = /expression\s*\(|url\s*\(/i

/**
 * 富文本档属性后处理（`style` 属性级收窄 + 图片协议拦截 + 外链安全属性强制）。
 *
 * DOMPurify 内建不清洗 `style` 取值、也不拦 `data:` 图片（`img` 属其 `DATA_URI_TAGS` 默认放行集），
 * 故在 `afterSanitizeAttributes` 钩子内按节点 §4 口径收口。
 *
 * @param node 当前元素。
 */
function hardenRichTextNode(node: Element): void {
  const style = node.getAttribute('style')
  if (style !== null) {
    const kept = style
      .split(';')
      .map((declaration) => declaration.trim())
      .filter((declaration) => declaration !== '')
      .filter((declaration) => {
        const name = declaration.split(':')[0]?.trim().toLowerCase() ?? ''
        return (RICH_TEXT_ALLOWED_STYLE_PROPS as readonly string[]).includes(name)
      })
      .filter((declaration) => !DANGEROUS_STYLE_VALUE.test(declaration))
    if (kept.length === 0) {
      node.removeAttribute('style')
    } else {
      node.setAttribute('style', kept.join('; '))
    }
  }

  const tag = node.tagName.toLowerCase()
  if (tag === 'img') {
    if (FORBIDDEN_IMG_SCHEME.test(node.getAttribute('src') ?? '')) {
      node.removeAttribute('src')
    }
    node.setAttribute('referrerpolicy', 'no-referrer')
  }
  if (tag === 'a' && node.getAttribute('target') === '_blank') {
    node.setAttribute('rel', 'noopener noreferrer')
  }
}

/**
 * 清洗富文本 HTML（去除脚本 / 事件属性 / 危险协议，仅保留白名单标签与属性）。
 *
 * @param html 原始 HTML。
 * @param profile 清洗档位（缺省 `strict`，既有调用零影响）。
 * @returns 清洗后的 HTML。
 */
export function sanitizeHtml(html: string, profile: SanitizeProfile = 'strict'): string {
  if (profile === 'strict') {
    return DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [...RICH_TEXT_ALLOWED_TAGS],
      ALLOWED_ATTR: [...RICH_TEXT_ALLOWED_ATTR],
      FORBID_ATTR: ['style'],
      ALLOW_DATA_ATTR: false,
    })
  }

  DOMPurify.addHook('afterSanitizeAttributes', hardenRichTextNode)
  try {
    return DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [...RICH_TEXT_ALLOWED_TAGS_PROFILE],
      ALLOWED_ATTR: [...RICH_TEXT_ALLOWED_ATTR_PROFILE],
      ALLOW_DATA_ATTR: false,
    })
  } finally {
    DOMPurify.removeHook('afterSanitizeAttributes')
  }
}

/**
 * 清洗 SVG 文本（自定义图标内联 SVG；仅启用 SVG 配置，第三方库单一落点）。
 *
 * @param svg 原始 SVG HTML。
 * @returns 清洗后的 SVG HTML。
 */
export function sanitizeSvg(svg: string): string {
  return DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } })
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
