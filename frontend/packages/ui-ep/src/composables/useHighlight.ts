/**
 * 只读高亮投影：核心编辑器内核能力基类 `BaseEditorKernel` 的薄投影；highlight.js 模块级缓存 + 按需语言注册。
 *
 * 具体件 `HighlightKernelState` **直接继承** `BaseEditorKernel`（经链上继承取得内核装配语义），
 * 浏览器 / 第三方库只在本投影与件内落点。
 */

import { BaseEditorKernel } from '@bms/core'
import type { HLJSApi } from 'highlight.js'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 模块级缓存（Promise 复用 → 不重复加载）。 */
let highlightPromise: Promise<HLJSApi> | undefined

/** 模块实际加载次数（测试断言恒为 1）。 */
let highlightLoads = 0

/** 已支持语言（未列出的按纯文本转义）。 */
export const HIGHLIGHT_LANGUAGES = ['sql', 'json', 'javascript'] as const

/**
 * 加载 highlight.js 核心与按需语言（模块级缓存）。
 *
 * @returns highlight.js 实例。
 */
export function loadHighlight(): Promise<HLJSApi> {
  if (!highlightPromise) {
    highlightLoads += 1
    highlightPromise = (async () => {
      const core = await import('highlight.js/lib/core')
      const hljs = core.default as HLJSApi
      const [sql, json, javascript] = await Promise.all([
        import('highlight.js/lib/languages/sql'),
        import('highlight.js/lib/languages/json'),
        import('highlight.js/lib/languages/javascript'),
      ])
      hljs.registerLanguage('sql', sql.default)
      hljs.registerLanguage('json', json.default)
      hljs.registerLanguage('javascript', javascript.default)
      return hljs
    })()
  }
  return highlightPromise
}

/** 取 highlight.js 模块加载次数（测试用）。 */
export function getHighlightLoadCount(): number {
  return highlightLoads
}

/** 重置模块缓存与计数（测试用）。 */
export function resetHighlightCache(): void {
  highlightPromise = undefined
  highlightLoads = 0
}

/**
 * 转义纯文本（无高亮语言或加载失败时降级）。
 *
 * @param code 原文。
 */
export function escapeHtml(code: string): string {
  return code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 高亮代码（语言不支持或失败时转义降级）。
 *
 * @param code 原文。
 * @param language 语言。
 * @returns 高亮 HTML。
 */
export async function highlightCode(code: string, language: string): Promise<string> {
  if (!HIGHLIGHT_LANGUAGES.includes(language as (typeof HIGHLIGHT_LANGUAGES)[number])) {
    return escapeHtml(code)
  }
  try {
    const hljs = await loadHighlight()
    return hljs.highlight(code, { language, ignoreIllegals: true }).value
  } catch {
    return escapeHtml(code)
  }
}

/** 具体高亮内核件（直接继承编辑器内核能力基类）。 */
class HighlightKernelState extends BaseEditorKernel {}

/** `useHighlight` 返回面。 */
export interface UseHighlightResult {
  /** 内核能力基类实例。 */
  kernel: BaseEditorKernel
  /** 是否已加载内核（响应式）。 */
  loaded: Ref<boolean>
  /** 加载 highlight.js（模块级缓存）。 */
  load: () => Promise<void>
  /** 高亮代码（不支持语言转义降级）。 */
  highlight: (code: string, language: string) => Promise<string>
}

/**
 * 使用只读高亮投影。
 *
 * @returns 运行时与加载 / 高亮方法。
 */
export function useHighlight(): UseHighlightResult {
  const kernel = new HighlightKernelState()
  kernel.mode = 'code'
  kernel.loader = () => loadHighlight()
  const loaded = ref(kernel.loaded)
  const off = kernel.onLifecycle((event) => {
    if (event === 'update') {
      loaded.value = kernel.loaded
    }
  })
  onScopeDispose(() => {
    off()
    kernel.dispose()
  })
  return {
    kernel,
    loaded,
    load: async () => {
      await kernel.load()
      loaded.value = kernel.loaded
    },
    highlight: async (code, language) => {
      await kernel.load()
      return highlightCode(code, language)
    },
  }
}
