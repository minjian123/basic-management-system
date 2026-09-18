<script setup lang="ts">
// 表达式编辑器件（08_02）：通用编辑内核（表达式语言）+ 字段 / 预置变量面板插入 + 运算符模板 + 校验入口。
import { computed, ref } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import CodeEditor, { type EditorDiagnostic } from './CodeEditor.vue'

/** 表达式令牌（字段 / 预置变量）。 */
export interface ExpressionToken {
  /** 标识。 */
  key: string
  /** 展示名。 */
  label: string
  /** 插入文本。 */
  insert: string
}

/** 表达式模板。 */
export interface ExpressionTemplate {
  /** 标识。 */
  key: string
  /** 模板名。 */
  label: string
  /** 表达式。 */
  expression: string
}

/** 表达式校验结果。 */
export interface ExpressionValidateResult {
  /** 是否合法。 */
  valid: boolean
  /** 诊断。 */
  diagnostics: EditorDiagnostic[]
}

interface Props {
  /** 表达式内容（受控）。 */
  modelValue?: string
  /** 只读。 */
  readOnly?: boolean
  /** 高度。 */
  height?: string
  /** 可用字段。 */
  fields?: ExpressionToken[]
  /** 预置变量。 */
  variables?: ExpressionToken[]
  /** 常用模板。 */
  templates?: ExpressionTemplate[]
  /** 外部诊断。 */
  diagnostics?: EditorDiagnostic[]
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  readOnly: false,
  height: '160px',
  fields: () => [],
  variables: () => [],
  templates: () => [],
  diagnostics: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  validate: [result: ExpressionValidateResult]
  insert: [payload: { token: ExpressionToken }]
}>()

const editor = ref<{ insert: (text: string) => void; getValue: () => string }>()
const innerDiagnostics = ref<EditorDiagnostic[]>([])
const { state, setState } = useBaseDataState()

/** 生效诊断。 */
const activeDiagnostics = computed(() =>
  props.diagnostics.length > 0 ? props.diagnostics : innerDiagnostics.value,
)

/** 插入令牌（字段 / 变量）。 */
function insertToken(token: ExpressionToken): void {
  editor.value?.insert(token.insert)
  emit('insert', { token })
}

/** 插入模板表达式。 */
function insertTemplate(template: ExpressionTemplate): void {
  editor.value?.insert(template.expression)
  emit('insert', { token: { key: template.key, label: template.label, insert: template.expression } })
}

/** 校验（前端轻校验：空内容视为合法；具体规则以后端接口为准）。 */
function runValidate(): ExpressionValidateResult {
  const value = editor.value?.getValue() ?? props.modelValue
  const diagnostics: EditorDiagnostic[] =
    value.trim() === '' ? [] : innerValidate(value)
  innerDiagnostics.value = diagnostics
  const result: ExpressionValidateResult = { valid: diagnostics.length === 0, diagnostics }
  setState(result.valid ? 'ready' : 'error')
  emit('validate', result)
  return result
}

/** 轻校验：括号配对与非法运算符（示例口径，后端强制）。 */
function innerValidate(value: string): EditorDiagnostic[] {
  const diagnostics: EditorDiagnostic[] = []
  const open = (value.match(/\(/g) ?? []).length
  const close = (value.match(/\)/g) ?? []).length
  if (open !== close) {
    diagnostics.push({ line: 1, severity: 'error', message: '括号不配对' })
  }
  return diagnostics
}
</script>

<template>
  <div class="bms-expression-editor" data-test="expression-editor" :data-state="state">
    <div class="bms-expression-editor__toolbar" data-test="toolbar">
      <button type="button" data-test="validate" :disabled="readOnly" @click="runValidate">校验</button>
    </div>
    <div class="bms-expression-editor__body">
      <CodeEditor
        ref="editor"
        :model-value="modelValue"
        language="expression"
        :read-only="readOnly"
        :height="height"
        :diagnostics="activeDiagnostics"
        @update:model-value="emit('update:modelValue', $event)"
      />
      <aside class="bms-expression-editor__panel" data-test="panel">
        <div v-if="fields.length > 0" data-test="fields">
          <strong>字段</strong>
          <button
            v-for="token in fields"
            :key="token.key"
            type="button"
            :data-test="`token-field-${token.key}`"
            @click="insertToken(token)"
          >
            {{ token.label }}
          </button>
        </div>
        <div v-if="variables.length > 0" data-test="variables">
          <strong>变量</strong>
          <button
            v-for="token in variables"
            :key="token.key"
            type="button"
            :data-test="`token-var-${token.key}`"
            @click="insertToken(token)"
          >
            {{ token.label }}
          </button>
        </div>
        <div v-if="templates.length > 0" data-test="templates">
          <strong>模板</strong>
          <button
            v-for="template in templates"
            :key="template.key"
            type="button"
            :data-test="`template-${template.key}`"
            @click="insertTemplate(template)"
          >
            {{ template.label }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>
