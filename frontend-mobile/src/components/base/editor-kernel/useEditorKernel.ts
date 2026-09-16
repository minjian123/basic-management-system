/**
 * 编辑器内核片段（`editor-kernel`）：编辑器内核的懒加载、挂载、销毁与内容协议。
 *
 * 契约见《组件设计 · 编辑器内核片段》：`loadKernel` / `create` / `destroy` / `getContent` /
 * `setContent` / `onChange`（CodeMirror 与富文本 / Markdown 共用）。
 * **占位先行**：未注入 `loader`（内核依赖未就绪）时 `loadKernel` 标记占位并返回 `null`，不动态 import、不报错。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 编辑器内核最小契约（各编辑器实现之） */
export interface EditorKernelInstance {
  getContent: () => string
  setContent: (content: string) => void
  focus?: () => void
  destroy: () => void
}

/** 内核装载器（动态 import 内核并初始化） */
export type EditorKernelLoader = (options: {
  kind: string
  language?: string
  readonly: boolean
  placeholder?: string
  onChange: (content: string) => void
}) => Promise<{ create: (el: HTMLElement) => EditorKernelInstance }>

/** 编辑器内核片段参数 */
export interface UseEditorKernelOptions {
  /** 内核类型（`codemirror` / `richtext` / `markdown`） */
  kind?: MaybeRefOrGetter<string>
  language?: MaybeRefOrGetter<string | undefined>
  readonly?: MaybeRefOrGetter<boolean>
  placeholder?: MaybeRefOrGetter<string>
  /** 装载器（缺省即占位：不加载内核） */
  loader?: EditorKernelLoader
  onChange?: (content: string) => void
}

/** 编辑器内核片段返回值 */
export interface UseEditorKernelReturn {
  readonly isLoaded: boolean
  readonly isPlaceholder: boolean
  readonly content: string
  readonly kind: string
  /** 懒加载内核（重复调用只加载一次） */
  loadKernel: () => Promise<void>
  /** 在元素上创建实例（自动先 `loadKernel`） */
  create: (el: HTMLElement) => Promise<EditorKernelInstance | null>
  destroy: () => void
  getContent: () => string
  setContent: (content: string) => void
  onChange: (cb: (content: string) => void) => void
}

/**
 * 获取编辑器内核能力。
 *
 * 用法：`const editor = useEditorKernel({ kind: 'codemirror', loader })`；
 * 内核依赖未就绪时省略 `loader` 即得占位行为（界面降级为只读文本框）。
 */
export function useEditorKernel(options: UseEditorKernelOptions = {}): UseEditorKernelReturn {
  const capability = declareFragment('editor-kernel')

  const isPlaceholder = computed(() => options.loader === undefined)
  const isLoaded = ref(false)
  const content = ref('')
  const callbacks: ((content: string) => void)[] = []
  let factory: { create: (el: HTMLElement) => EditorKernelInstance } | undefined
  let instance: EditorKernelInstance | undefined

  const emitChange = (next: string): void => {
    content.value = next
    options.onChange?.(next)
    for (const cb of callbacks) {
      cb(next)
    }
  }

  const loadKernel = async (): Promise<void> => {
    if (isLoaded.value || !options.loader) {
      if (!options.loader) {
        capability.log('debug', 'editor-kernel 占位：内核装载器未接入，跳过加载')
      }
      return
    }
    factory = await options.loader({
      kind: String(toValue(options.kind) ?? 'codemirror'),
      language: toValue(options.language),
      readonly: Boolean(toValue(options.readonly)),
      placeholder: toValue(options.placeholder),
      onChange: emitChange,
    })
    isLoaded.value = true
  }

  const create = async (el: HTMLElement): Promise<EditorKernelInstance | null> => {
    await loadKernel()
    if (!factory) {
      return null
    }
    destroy()
    instance = factory.create(el)
    return instance
  }

  const destroy = (): void => {
    if (!instance) {
      return
    }
    try {
      instance.destroy()
    } catch (error) {
      capability.reportError(error, { scope: 'editor-kernel.destroy' })
    }
    instance = undefined
  }

  return {
    get isLoaded() {
      return isLoaded.value
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get content() {
      return content.value
    },
    get kind() {
      return String(toValue(options.kind) ?? 'codemirror')
    },
    loadKernel,
    create,
    destroy,
    getContent: () => instance?.getContent() ?? content.value,
    setContent: (next) => {
      content.value = next
      instance?.setContent(next)
    },
    onChange: (cb) => {
      callbacks.push(cb)
    },
  }
}
