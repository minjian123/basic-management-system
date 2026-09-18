<script setup lang="ts">
// 通用编辑器件（08_02）：内核经 BaseEditorKernel 复用（CodeMirror 模块级缓存），能力缺失降级为纯文本域。
import { defineAsyncComponent, onMounted, ref, shallowRef, watch, type Component } from 'vue'

import { useCodeKernel } from '../../composables/useCodeKernel'

/** 编辑器语言。 */
export type EditorLanguage = 'sql' | 'expression' | 'cron' | 'json' | 'javascript' | 'text'

/** 编辑器诊断。 */
export interface EditorDiagnostic {
  /** 行号（从 1 起）。 */
  line: number
  /** 列号。 */
  column?: number
  /** 级别。 */
  severity: 'error' | 'warning' | 'info'
  /** 说明。 */
  message: string
}

const AsyncHost = defineAsyncComponent(() => import('./CodeMirrorHost.vue'))

interface Props {
  /** 内容（受控）。 */
  modelValue?: string
  /** 语言。 */
  language?: EditorLanguage
  /** 只读。 */
  readOnly?: boolean
  /** 高度。 */
  height?: string
  /** 是否显示行号。 */
  lineNumbers?: boolean
  /** 占位文案。 */
  placeholder?: string
  /** 缩进空格数。 */
  indent?: number
  /** 主题。 */
  theme?: 'auto' | 'light' | 'dark'
  /** 诊断（内联标注 / 底部汇总）。 */
  diagnostics?: EditorDiagnostic[]
  /** 强制纯文本降级（能力缺失场景）。 */
  plain?: boolean
  /** 编辑宿主覆盖（测试或定制，缺省异步 CodeMirror）。 */
  host?: Component
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  language: 'text',
  readOnly: false,
  height: '160px',
  lineNumbers: true,
  placeholder: '',
  indent: 2,
  theme: 'auto',
  diagnostics: () => [],
  plain: false,
  host: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  validate: [diagnostics: EditorDiagnostic[]]
  ready: []
}>()

const kernel = useCodeKernel()
const content = ref(props.modelValue)
const kernelReady = ref(false)
const kernelFailed = ref(false)
const hostError = ref(false)

watch(
  () => props.modelValue,
  (value) => {
    content.value = value
  },
)

onMounted(async () => {
  try {
    await kernel.load()
    kernelReady.value = true
    emit('ready')
  } catch {
    kernelFailed.value = true
  }
})

/** 生效宿主（内核未就绪 / 强制纯文本时为空 → 走文本域降级）。 */
const activeHost = shallowRef<Component | undefined>()
watch(
  [kernelReady, kernelFailed, () => props.plain, () => props.host],
  () => {
    activeHost.value =
      kernelReady.value && !kernelFailed.value && !props.plain ? (props.host ?? AsyncHost) : undefined
  },
  { immediate: true },
)

/** 内容变更（同步受控与变更事件）。 */
function onChange(value: string): void {
  content.value = value
  emit('update:modelValue', value)
  emit('change', value)
}

/** 聚焦编辑器。 */
function focus(): void {
  const element = document.querySelector('.bms-code-editor textarea') as HTMLTextAreaElement | null
  element?.focus()
}

/** 取当前内容。 */
function getValue(): string {
  return content.value
}

/** 设置内容。 */
function setValue(value: string): void {
  onChange(value)
}

/** 在末尾插入片段。 */
function insert(text: string): void {
  onChange(content.value + text)
}

/** 取选区（纯文本降级无选区，返回空串）。 */
function getSelection(): string {
  return ''
}

defineExpose({ focus, getValue, setValue, insert, getSelection })
</script>

<template>
  <div
    class="bms-code-editor"
    data-test="code-editor"
    :data-language="language"
    :data-ready="kernelReady || undefined"
    :data-failed="kernelFailed || hostError || undefined"
    :data-readonly="readOnly || undefined"
  >
    <component
      :is="activeHost"
      v-if="activeHost"
      :model-value="content"
      :language="language"
      :read-only="readOnly"
      :indent="indent"
      :line-numbers="lineNumbers"
      :diagnostics="diagnostics"
      @change="onChange"
      @error="hostError = true"
    />
    <textarea
      v-else
      class="bms-code-editor__fallback"
      data-test="code-fallback"
      :value="content"
      :readonly="readOnly"
      :placeholder="placeholder"
      :style="{ height }"
      @input="onChange(($event.target as HTMLTextAreaElement).value)"
    />
    <ul v-if="diagnostics.length > 0" class="bms-code-editor__diagnostics" data-test="diagnostics">
      <li v-for="(item, index) in diagnostics" :key="index" :data-severity="item.severity">
        {{ item.line }}:{{ item.column ?? 1 }} {{ item.message }}
      </li>
    </ul>
  </div>
</template>
