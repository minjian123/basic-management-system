/**
 * AI 消息 Markdown 渲染（08_10）：`marked` 动态加载（AI 分包内，不进首屏）+ DOMPurify 白名单清洗。
 *
 * 代码围栏分段经 `splitContentSegments`（核心领域纯函数）交给调用方走只读高亮；
 * `marked` 加载失败时降级为纯文本转义（不抛错）。
 */

import { splitContentSegments } from '@bms/core'

import { escapeHtml } from '../composables/useHighlight'
import { sanitizeHtml } from './sanitizeHtml'

/** Markdown 解析函数（加载后就位）。 */
let markdownParse: ((source: string) => string) | undefined

/** 在途加载 Promise（并发去重）。 */
let loadingPromise: Promise<void> | undefined

/**
 * 加载 `marked` 解析器（幂等；失败降级不抛错）。
 *
 * @returns 加载完成 Promise。
 */
export async function loadMarked(): Promise<void> {
  if (markdownParse !== undefined) {
    return
  }
  if (loadingPromise === undefined) {
    loadingPromise = import('marked')
      .then((module) => {
        markdownParse = (source: string) =>
          module.marked.parse(source, { async: false, gfm: true, breaks: true }) as string
      })
      .catch(() => {
        loadingPromise = undefined
      })
  }
  await loadingPromise
}

/**
 * 渲染 Markdown 为安全 HTML（富文本白名单清洗）。
 *
 * @param content Markdown 文本。
 * @returns 清洗后的 HTML（`marked` 未就绪时降级为转义纯文本）。
 */
export async function renderAiMarkdown(content: string): Promise<string> {
  if (content === '') {
    return ''
  }
  await loadMarked()
  const html =
    markdownParse !== undefined ? markdownParse(content) : escapeHtml(content).replace(/\n/g, '<br>')
  return sanitizeHtml(html)
}

/**
 * 分段为文本段与围栏代码段（文本走 Markdown、代码走只读高亮）。
 *
 * @param content 消息内容。
 * @returns 分段数组。
 */
export function splitAiContent(content: string): { type: 'text' | 'code'; text: string; lang?: string }[] {
  return splitContentSegments(content)
}

/**
 * 重置 `marked` 缓存（测试用）。
 */
export function resetMarkedCache(): void {
  markdownParse = undefined
  loadingPromise = undefined
}
