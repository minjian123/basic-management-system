/** 编辑内核投影：把核心编辑器内核能力基类 `BaseEditorKernel` 投影为组合式；CodeMirror 模块级缓存，多次使用不重复加载。 */

import { BaseEditorKernel } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** CodeMirror 模块集合（懒加载结果，类型宽松由宿主收窄）。 */
export interface CodeModules {
  /** 基础扩展。 */
  basicSetup: unknown
  /** 编辑器视图构造器。 */
  EditorView: unknown
  /** 编辑器状态构造器。 */
  EditorState: unknown
  /** 只读 facet。 */
  readOnly: { of: (value: boolean) => unknown }
  /** 可编辑 facet。 */
  editable: { of: (value: boolean) => unknown }
  /** SQL 语言扩展。 */
  sql: ((config?: unknown) => unknown) | undefined
  /** JSON 语言扩展。 */
  json: (() => unknown) | undefined
  /** JavaScript 语言扩展。 */
  javascript: ((config?: { jsx?: boolean; typescript?: boolean }) => unknown) | undefined
}

/** 模块级缓存（Promise 复用 → 不重复加载）。 */
let codeModulesPromise: Promise<CodeModules> | undefined

/** 模块实际加载次数（测试断言恒为 1）。 */
let codeModuleLoads = 0

/**
 * 加载 CodeMirror 模块（模块级缓存，多次调用只加载一次）。
 *
 * @returns 模块集合。
 */
export function loadCodeModules(): Promise<CodeModules> {
  if (!codeModulesPromise) {
    codeModuleLoads += 1
    codeModulesPromise = Promise.all([
      import('codemirror'),
      import('@codemirror/state'),
      import('@codemirror/lang-sql'),
      import('@codemirror/lang-json'),
      import('@codemirror/lang-javascript'),
    ]).then(([cm, state, sql, json, javascript]) => {
      const stateCtor = state.EditorState as unknown as { readOnly: { of: (value: boolean) => unknown } }
      const viewCtor = cm.EditorView as unknown as { editable: { of: (value: boolean) => unknown } }
      return {
        basicSetup: cm.basicSetup,
        EditorView: cm.EditorView,
        EditorState: state.EditorState,
        readOnly: stateCtor.readOnly,
        editable: viewCtor.editable,
        sql: sql.sql as (config?: unknown) => unknown,
        json: json.json as () => unknown,
        javascript: javascript.javascript as (config?: { jsx?: boolean; typescript?: boolean }) => unknown,
      }
    })
  }
  return codeModulesPromise
}

/** 取 CodeMirror 模块加载次数（测试用）。 */
export function getCodeModuleLoadCount(): number {
  return codeModuleLoads
}

/** 重置模块缓存与计数（测试用）。 */
export function resetCodeModuleCache(): void {
  codeModulesPromise = undefined
  codeModuleLoads = 0
}

/** 具体编辑内核（可实例化）。 */
class CodeKernelState extends BaseEditorKernel {}

/** `useCodeKernel` 返回面。 */
export interface UseCodeKernelResult {
  /** 编辑内核基类实例。 */
  kernel: BaseEditorKernel
  /** 是否已加载内核（响应式）。 */
  loaded: Ref<boolean>
  /** 加载内核（复用模块级缓存）。 */
  load: () => Promise<void>
  /** 销毁内核。 */
  destroy: () => void
}

/**
 * 使用编辑内核投影。
 *
 * @returns 编辑内核基类实例与响应式面。
 */
export function useCodeKernel(): UseCodeKernelResult {
  const kernel = new CodeKernelState()
  kernel.mode = 'code'
  kernel.loader = () => loadCodeModules()
  const loaded = ref(kernel.loaded)
  const off = kernel.onLifecycle((event) => {
    if (event === 'update') {
      loaded.value = kernel.loaded
    }
  })
  onScopeDispose(off)

  return {
    kernel,
    loaded,
    load: async () => {
      await kernel.load()
      loaded.value = kernel.loaded
    },
    destroy: () => {
      kernel.destroy()
      loaded.value = kernel.loaded
    },
  }
}
