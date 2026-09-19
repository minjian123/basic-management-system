<script setup lang="ts">
// 节点属性面板件（08_8_2）：自建面板（不引官方 properties-panel）；按元素类型渲染可配项；条件表达式复用表达式编辑内核；必填与枚举即时校验。
import {
  propertiesFor,
  validateProperties,
  type ModelerElementProperties,
  type ModelerElementType,
  type ModelerPropertyItem,
  type ModelerValidateError,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseProcessModeler } from '../../composables/useBaseProcessModeler'
import ExpressionEditor, {
  type ExpressionTemplate,
  type ExpressionToken,
} from '../interaction/ExpressionEditor.vue'

interface Props {
  /** 当前属性值。 */
  properties?: ModelerElementProperties
  /** 选中元素类型。 */
  selectedType?: ModelerElementType
  /** 选中元素标识。 */
  selectedId?: string
  /** 流程级属性（未选中时展示）。 */
  definitionKey?: string
  /** 流程级名称。 */
  definitionName?: string
  /** 只读。 */
  readOnly?: boolean
  /** 条件表达式可用字段令牌。 */
  expressionFields?: ExpressionToken[]
  /** 条件表达式预置变量令牌。 */
  expressionVariables?: ExpressionToken[]
  /** 条件表达式模板。 */
  expressionTemplates?: ExpressionTemplate[]
  /** 外部校验错误（引擎预解析结论）。 */
  errors?: readonly ModelerValidateError[]
}

const props = withDefaults(defineProps<Props>(), {
  properties: () => ({}),
  selectedType: undefined,
  selectedId: '',
  definitionKey: '',
  definitionName: '',
  readOnly: false,
  expressionFields: () => [],
  expressionVariables: () => [],
  expressionTemplates: () => [],
  errors: () => [],
})

const emit = defineEmits<{
  'property-change': [payload: { key: keyof ModelerElementProperties; value: unknown }]
  validate: [payload: { valid: boolean; errors: readonly ModelerValidateError[] }]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { modeler } = useBaseProcessModeler()

/** 本地草稿（受控件未接 `v-model` 时按本地草稿即时渲染）。 */
const draft = ref<ModelerElementProperties>({ ...props.properties })

watch(
  () => props.properties,
  (value) => {
    draft.value = { ...value }
  },
  { deep: true },
)

/** 可用属性项。 */
const schema = computed<ModelerPropertyItem[]>(() => propertiesFor(props.selectedType))

/** 内部校验错误。 */
const errors = computed(() => validateProperties(props.selectedType, draft.value).errors)

/**
 * 写入属性（同步本地草稿并上抛；同步推送校验结论）。
 *
 * @param key 属性键。
 * @param value 属性值。
 */
function write(key: keyof ModelerElementProperties, value: unknown): void {
  draft.value = { ...draft.value, [key]: value }
  emit('property-change', { key, value })
  const result = validateProperties(props.selectedType, draft.value)
  emit('validate', { valid: result.valid, errors: result.errors })
}

/**
 * 取属性项错误文案。
 *
 * @param key 属性键。
 * @returns 错误文案（无则空串）。
 */
function errorOf(key: keyof ModelerElementProperties): string {
  const table: Partial<Record<keyof ModelerElementProperties, string>> = {
    name: '节点名称必填',
    assigneeSource: '审批人来源必填且在枚举内',
    assigneeValue: '审批人取值必填',
    multiRule: '多人规则必填且在枚举内',
    timeoutValue: '超时须为正数',
    condition: '非默认流须填写条件表达式',
  }
  const hit = errors.value.some((error) => error.message === table[key])
  return hit ? (table[key] ?? '') : ''
}

// 说明：`modeler` 仅为挂链（件层以投影组合式接入继承链）。
void modeler

defineExpose({ draft, errors })
</script>

<template>
  <div class="bms-process-properties" data-test="process-properties">
    <p v-if="selectedId === ''" class="bms-process-properties__empty" data-test="properties-empty">
      未选中元素 · 流程：{{ definitionKey }}（{{ definitionName }}）
    </p>

    <template v-else>
      <p class="bms-process-properties__selected" data-test="properties-selected">
        {{ selectedId }}（{{ selectedType }}）
      </p>
      <label v-for="item in schema" :key="item.key" class="bms-process-properties__field" :data-test="`property-${item.key}`">
        <span class="bms-process-properties__label">{{ item.label }}</span>

        <select
          v-if="item.kind === 'select'"
          :value="(draft[item.key] as string) ?? ''"
          :disabled="readOnly"
          @change="write(item.key, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">请选择</option>
          <option v-for="option in item.options ?? []" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>

        <input
          v-else-if="item.kind === 'number'"
          type="number"
          :value="(draft[item.key] as number | undefined) ?? ''"
          :disabled="readOnly"
          @input="write(item.key, Number(($event.target as HTMLInputElement).value))"
        />

        <input
          v-else-if="item.kind === 'switch'"
          type="checkbox"
          :checked="draft[item.key] === true"
          :disabled="readOnly"
          @change="write(item.key, ($event.target as HTMLInputElement).checked)"
        />

        <ExpressionEditor
          v-else-if="item.kind === 'expression'"
          data-test="condition-editor"
          :model-value="(draft[item.key] as string) ?? ''"
          :fields="expressionFields"
          :variables="expressionVariables"
          :templates="expressionTemplates"
          :read-only="readOnly"
          @update:model-value="write(item.key, $event)"
        />

        <input
          v-else
          type="text"
          :value="(draft[item.key] as string) ?? ''"
          :placeholder="item.placeholder"
          :disabled="readOnly"
          @input="write(item.key, ($event.target as HTMLInputElement).value)"
        />

        <span v-if="errorOf(item.key) !== ''" class="bms-process-properties__error" :data-test="`property-error-${item.key}`">
          {{ errorOf(item.key) }}
        </span>
      </label>

      <ul v-if="errors.length > 0" class="bms-process-properties__errors">
        <li v-for="(error, index) in errors" :key="index">{{ error.message }}</li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.bms-process-properties {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-process-properties__field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bms-process-properties__label {
  color: var(--bms-color-text-secondary, #909399);
  font-size: 0.85em;
}

.bms-process-properties__field input,
.bms-process-properties__field select {
  padding: 4px 6px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 2px);
  font: inherit;
}

.bms-process-properties__error,
.bms-process-properties__errors {
  color: var(--bms-color-danger, #f56c6c);
  font-size: 0.85em;
}

.bms-process-properties__empty,
.bms-process-properties__selected {
  margin: 0;
  color: var(--bms-color-text-secondary, #909399);
  font-size: 0.9em;
}
</style>
