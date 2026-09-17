/**
 * 编辑器域组合式（`useEditorBase`）：编辑器域基类的组合轨。
 *
 * 契约见《组件设计 · 编辑器域基类》：组合 `useEditorKernel`（懒加载 / 创建销毁 / 内容协议），
 * 统一受控内容、即时受控上报 + 去抖业务上报、只读、挂卸与**富文本白名单净化**。
 * **占位先行**：未注入 `loader` 时不加载内核（降级为 textarea，由组件包装兜底）。
 * 依赖方向：片段 + Vue；内核（CodeMirror / 富文本）由 `loader` 注入、独立分包。
 */

import { computed, onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { useEditorKernel, type EditorKernelLoader } from '../editor-kernel/useEditorKernel'

/** 编辑器种类（内容协议：rich＝HTML / markdown＝Markdown 文本 / code＝纯文本） */
export type EditorKind = 'rich' | 'markdown' | 'code'

/** 编辑器域组合式参数 */
export interface UseEditorBaseOptions {
  modelValue?: MaybeRefOrGetter<string>
  kind?: MaybeRefOrGetter<EditorKind>
  language?: MaybeRefOrGetter<string>
  readonly?: MaybeRefOrGetter<boolean>
  placeholder?: MaybeRefOrGetter<string>
  /** `change` 去抖毫秒数（缺省 300） */
  debounce?: number
  /** 内核装载器（缺省即占位：不加载内核） */
  loader?: EditorKernelLoader
  /** 即时上报（受控写入，随每次输入） */
  onUpdate?: (content: string) => void
  /** 去抖上报（业务变更） */
  onChange?: (content: string) => void
}

/** 编辑器域组合式返回值 */
export interface UseEditorBaseReturn {
  readonly content: string
  readonly kind: string
  readonly isLoaded: boolean
  readonly isPlaceholder: boolean
  readonly readonly: boolean
  /** 在容器上创建内核实例（内部先懒加载内核） */
  mount: (el: HTMLElement) => Promise<void>
  /** 销毁内核实例（组件卸载自动调用；同时清理未触发的去抖定时器） */
  unmount: () => void
  setContent: (content: string) => void
  getContent: () => string
  focus: () => void
  blur: () => void
  /** 统一输入入口（降级 textarea 与内核变更均走此口） */
  onInput: (content: string) => void
  /** 按 `kind` 净化（`rich` 走白名单，其余原样） */
  sanitize: (html: string) => string
}

/** 富文本白名单标签 */
const ALLOWED_TAGS = new Set([
  'p',
  'br',
  'strong',
  'b',
  'em',
  'i',
  'u',
  's',
  'del',
  'a',
  'ul',
  'ol',
  'li',
  'blockquote',
  'code',
  'pre',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'img',
  'span',
  'div',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
])

/** 危险标签（整块剔除，含内容；防 XSS 与样式注入） */
const DANGEROUS_TAGS = new Set(['script', 'style', 'iframe', 'object', 'embed', 'link', 'meta'])

/** 标签级白名单属性 */
const ALLOWED_ATTRS: Record<string, readonly string[]> = {
  a: ['href', 'title', 'target'],
  img: ['src', 'alt', 'title'],
  td: ['colspan', 'rowspan'],
  th: ['colspan', 'rowspan'],
}

/**
 * 富文本白名单净化（前端第一道；服务端二次净化为最终防线）。
 *
 * 剔除：非白名单标签（解包保留内容）、`on*` 事件属性、`javascript:` / `data:text/html` 地址、
 * 非白名单属性；`script` / `style` 等标签内容随标签一并剔除。
 */
export function sanitizeHtml(html: string): string {
  if (typeof document === 'undefined') {
    return html
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
      .replace(/javascript:/gi, '')
  }
  const template = document.createElement('template')
  template.innerHTML = html
  const clean = (element: Element): void => {
    for (const child of Array.from(element.children)) {
      clean(child)
    }
    const tag = element.tagName.toLowerCase()
    if (DANGEROUS_TAGS.has(tag)) {
      element.remove()
      return
    }
    if (!ALLOWED_TAGS.has(tag)) {
      const parent = element.parentNode
      if (parent) {
        while (element.firstChild) {
          parent.insertBefore(element.firstChild, element)
        }
        parent.removeChild(element)
      }
      return
    }
    const allowed = ALLOWED_ATTRS[tag] ?? []
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase()
      const isEvent = name.startsWith('on')
      const isScriptUrl = /^\s*(javascript|data:text\/html)/i.test(attribute.value)
      if (isEvent || isScriptUrl || !allowed.includes(name)) {
        element.removeAttribute(attribute.name)
      }
    }
  }
  for (const child of Array.from(template.content.children)) {
    clean(child)
  }
  return template.innerHTML
}

/**
 * 获取编辑器域能力。
 *
 * 用法：`const editor = useEditorBase({ modelValue, kind: 'rich', loader, onChange })`；
 * 省略 `loader` 即得占位行为（组件层降级 textarea）。
 */
export function useEditorBase(options: UseEditorBaseOptions = {}): UseEditorBaseReturn {
  const kernel = useEditorKernel({
    ...(options.kind !== undefined ? { kind: options.kind } : {}),
    ...(options.language !== undefined ? { language: options.language } : {}),
    ...(options.readonly !== undefined ? { readonly: options.readonly } : {}),
    ...(options.placeholder !== undefined ? { placeholder: options.placeholder } : {}),
    ...(options.loader ? { loader: options.loader } : {}),
  })

  const kind = computed(() => String(toValue(options.kind) ?? 'rich'))
  const readonly = computed(() => Boolean(toValue(options.readonly)))
  const content = ref(kernel.content)
  const debounceMs = options.debounce ?? 300
  let timer: ReturnType<typeof setTimeout> | undefined
  let container: HTMLElement | undefined

  const cancelPending = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
  }

  watch(
    () => (options.modelValue === undefined ? undefined : String(toValue(options.modelValue))),
    (next) => {
      if (next === undefined || next === content.value) {
        return
      }
      content.value = next
      kernel.setContent(next)
    },
    { immediate: true },
  )

  const sanitize = (html: string): string => (kind.value === 'rich' ? sanitizeHtml(html) : html)

  const setContent = (next: string): void => {
    const value = sanitize(next)
    content.value = value
    kernel.setContent(value)
  }

  const getContent = (): string => sanitize(kernel.getContent())

  const onInput = (next: string): void => {
    content.value = next
    options.onUpdate?.(next)
    cancelPending()
    timer = setTimeout(() => {
      timer = undefined
      options.onChange?.(content.value)
      kernel.setContent(content.value)
    }, debounceMs)
  }

  const mount = async (el: HTMLElement): Promise<void> => {
    container = el
    await kernel.create(el)
    if (kernel.isLoaded) {
      kernel.setContent(content.value)
    }
  }

  const unmount = (): void => {
    cancelPending()
    container = undefined
    kernel.destroy()
  }

  onScopeDispose(() => {
    cancelPending()
  })

  return {
    get content() {
      return content.value
    },
    get kind() {
      return kind.value
    },
    get isLoaded() {
      return kernel.isLoaded
    },
    get isPlaceholder() {
      return kernel.isPlaceholder
    },
    get readonly() {
      return readonly.value
    },
    mount,
    unmount,
    setContent,
    getContent,
    focus: () => {
      container?.focus()
    },
    blur: () => {
      container?.blur()
    },
    onInput,
    sanitize,
  }
}
