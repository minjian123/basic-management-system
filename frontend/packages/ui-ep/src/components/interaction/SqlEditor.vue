<script setup lang="ts">
// SQL 编辑器件（08_02）：通用编辑内核（SQL 语言）+ 仅 SELECT 轻校验 + 格式化 / 测试执行入口 + 字段清单插入。
// 样式（11-01）：工具栏改 el-button、字段清单改 el-button 列名，补 <style scoped> 消费 --bms-* 令牌。
import { ElButton } from 'element-plus'
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
      <el-button data-test="format" size="small" :disabled="readOnly" @click="emit('format')">格式化</el-button>
      <el-button data-test="validate" size="small" :disabled="readOnly" @click="runValidate">校验</el-button>
      <el-button data-test="test" size="small" type="primary" :disabled="readOnly || !canTest" @click="emit('test')">
        测试执行
      </el-button>
    </div>
    <div class="bms-sql-editor__body">
      <div class="bms-sql-editor__main">
        <CodeEditor
          ref="editor"
          :model-value="modelValue"
          language="sql"
          :read-only="readOnly"
          :height="height"
          :diagnostics="activeDiagnostics"
          @update:model-value="emit('update:modelValue', $event)"
        />
      </div>
      <aside v-if="fields.length > 0" class="bms-sql-editor__fields" data-test="fields">
        <strong class="bms-sql-editor__fields-title">字段清单</strong>
        <div class="bms-sql-editor__field-list">
          <el-button
            v-for="field in fields"
            :key="field.name"
            :data-test="`field-${field.name}`"
            size="small"
            @click="insertField(field.name)"
          >
            {{ field.name }}（{{ field.type }}）
          </el-button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.bms-sql-editor {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-sql-editor__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-sql-editor__body {
  display: flex;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-sql-editor__main {
  flex: 1;
  min-width: 0;
}

.bms-sql-editor__fields {
  display: flex;
  flex: none;
  flex-direction: column;
  gap: var(--bms-space-2);
  width: 200px;
  max-height: 100%;
  padding: var(--bms-space-3);
  overflow: auto;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-sql-editor__fields-title {
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
}

.bms-sql-editor__field-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-1);
}

.bms-sql-editor[data-state='error'] .bms-sql-editor__fields {
  border-color: var(--bms-color-danger);
}

@media (max-width: 992px) {
  .bms-sql-editor__body {
    flex-direction: column;
  }

  .bms-sql-editor__fields {
    width: 100%;
  }
}
</style>

