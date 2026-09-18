<script setup lang="ts">
// SQL 编辑器件（08_02）：通用编辑内核（SQL 语言）+ 仅 SELECT 轻校验 + 格式化 / 测试执行入口 + 字段清单插入。
import { computed, ref } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import CodeEditor, { type EditorDiagnostic } from './CodeEditor.vue'

/** SQL 校验结果。 */
export interface SqlValidateResult {
  /** 是否合法。 */
  valid: boolean
  /** 诊断。 */
  diagnostics: EditorDiagnostic[]
}

interface Props {
  /** SQL 内容（受控）。 */
  modelValue?: string
  /** 只读。 */
  readOnly?: boolean
  /** 高度。 */
  height?: string
  /** 是否可测试执行（`rpt:design`）。 */
  canTest?: boolean
  /** 字段清单（可插入列名）。 */
  fields?: { name: string; type: string }[]
  /** 外部诊断。 */
  diagnostics?: EditorDiagnostic[]
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  readOnly: false,
  height: '200px',
  canTest: false,
  fields: () => [],
  diagnostics: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  validate: [result: SqlValidateResult]
  test: []
  format: []
  'insert-field': [name: string]
}>()

const editor = ref<{ insert: (text: string) => void; getValue: () => string }>()
const innerDiagnostics = ref<EditorDiagnostic[]>([])
const { state, setState } = useBaseDataState()

/** 生效诊断（外部优先，否则取本地轻校验）。 */
const activeDiagnostics = computed(() =>
  props.diagnostics.length > 0 ? props.diagnostics : innerDiagnostics.value,
)

/** 前端轻校验（仅 SELECT；以后端校验为准）。 */
function runValidate(): SqlValidateResult {
  const value = editor.value?.getValue() ?? props.modelValue
  const trimmed = value.trim()
  let result: SqlValidateResult
  if (trimmed === '') {
    result = { valid: true, diagnostics: [] }
  } else if (!/^select\b/i.test(trimmed)) {
    result = {
      valid: false,
      diagnostics: [{ line: 1, severity: 'error', message: '仅支持 SELECT 查询' }],
    }
  } else {
    result = { valid: true, diagnostics: [] }
  }
  innerDiagnostics.value = result.diagnostics
  setState(result.valid ? 'ready' : 'error')
  emit('validate', result)
  return result
}

/** 插入字段名到光标处（此处追加到末尾）。 */
function insertField(name: string): void {
  editor.value?.insert(name)
  emit('insert-field', name)
}
</script>

<template>
  <div class="bms-sql-editor" data-test="sql-editor" :data-state="state">
    <div class="bms-sql-editor__toolbar" data-test="toolbar">
      <button type="button" data-test="format" :disabled="readOnly" @click="emit('format')">格式化</button>
      <button type="button" data-test="validate" :disabled="readOnly" @click="runValidate">校验</button>
      <button type="button" data-test="test" :disabled="readOnly || !canTest" @click="emit('test')">测试执行</button>
    </div>
    <div class="bms-sql-editor__body">
      <CodeEditor
        ref="editor"
        :model-value="modelValue"
        language="sql"
        :read-only="readOnly"
        :height="height"
        :diagnostics="activeDiagnostics"
        @update:model-value="emit('update:modelValue', $event)"
      />
      <aside v-if="fields.length > 0" class="bms-sql-editor__fields" data-test="fields">
        <button
          v-for="field in fields"
          :key="field.name"
          type="button"
          :data-test="`field-${field.name}`"
          @click="insertField(field.name)"
        >
          {{ field.name }}（{{ field.type }}）
        </button>
      </aside>
    </div>
  </div>
</template>
