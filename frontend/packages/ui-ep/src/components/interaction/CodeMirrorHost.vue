<script setup lang="ts">
// CodeMirror 6 宿主（08_02）：由 CodeEditor 异步懒加载的独立分包入口；内核模块经 useCodeKernel 模块级缓存复用。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { loadCodeModules, useCodeKernel, type CodeModules } from '../../composables/useCodeKernel'
import type { EditorDiagnostic } from './CodeEditor.vue'

interface CmView {
  state: { doc: { toString(): string } }
  destroy: () => void
}

interface CmViewStatic {
  new (config: { state: unknown; parent: unknown }): CmView
  updateListener: {
    of: (listener: (update: { docChanged: boolean; state: { doc: { toString(): string } } }) => void) => unknown
  }
}

interface CmStateStatic {
  new (config: { doc: string; extensions: unknown[] }): unknown
}

interface Props {
  /** 内容（受控）。 */
  modelValue?: string
  /** 语言。 */
  language?: string
  /** 只读。 */
  readOnly?: boolean
  /** 缩进空格数。 */
  indent?: number
  /** 是否显示行号。 */
  lineNumbers?: boolean
  /** 诊断。 */
  diagnostics?: EditorDiagnostic[]
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  language: 'text',
  readOnly: false,
  indent: 2,
  lineNumbers: true,
  diagnostics: () => [],
})

const emit = defineEmits<{
  change: [value: string]
  ready: []
  error: []
}>()

const { kernel } = useCodeKernel()
const container = ref<HTMLElement>()
const failed = ref(false)
let view: CmView | undefined
let modules: CodeModules | undefined

/** 语言扩展（按 language 选择语言包；未知语言纯文本）。 */
function languageExtension(): unknown {
  if (!modules) {
    return undefined
  }
  if (props.language === 'sql' || props.language === 'expression') {
    return modules.sql?.()
  }
  if (props.language === 'json') {
    return modules.json?.()
  }
  if (props.language === 'javascript') {
    return modules.javascript?.({})
  }
  return undefined
}

onMounted(async () => {
  if (!container.value) {
    return
  }
  try {
    await kernel.load()
    modules = await loadCodeModules()
    const EditorView = modules.EditorView as unknown as CmViewStatic
    const EditorState = modules.EditorState as unknown as CmStateStatic
    const extensions: unknown[] = [
      modules.basicSetup,
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          emit('change', update.state.doc.toString())
        }
      }),
      modules.editable.of(!props.readOnly),
      modules.readOnly.of(props.readOnly),
    ]
    const language = languageExtension()
    if (language !== undefined && language !== null) {
      extensions.push(language)
    }
    view = new EditorView({
      state: new EditorState({ doc: props.modelValue, extensions }),
      parent: container.value,
    })
    failed.value = false
    emit('ready')
  } catch {
    failed.value = true
    emit('error')
  }
})

onBeforeUnmount(() => {
  view?.destroy()
  view = undefined
})
</script>

<template>
  <div
    class="bms-code-mirror-host"
    data-test="cm-host"
    data-subpackage="codemirror"
    :data-language="language"
    :data-readonly="readOnly"
    :data-diagnostics="diagnostics.length"
    :data-failed="failed || undefined"
  >
    <div ref="container" class="bms-code-mirror-host__mount" />
    <p v-if="failed" class="bms-code-mirror-host__error" data-test="cm-error">编辑内核不可用，已降级为纯文本</p>
  </div>
</template>
