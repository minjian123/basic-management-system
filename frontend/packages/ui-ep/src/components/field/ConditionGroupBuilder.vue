<script setup lang="ts">
// 条件组构建件（06_06）：AND/OR 分组树 + 字段与操作符联动 + 增删条件 / 子组（深度受限）；可独立复用（列表筛选区）。
import {
  DICT_CONDITION_MAX_DEPTH,
  DICT_OPERATOR_TEXTS,
  defaultOperatorsOf,
  isOperatorAllowed,
  type DictAttrFieldOption,
  type DictConditionGroup,
  type DictConditionItem,
  type DictOperator,
} from '@bms/core'
import { ElButton, ElInput, ElOption, ElSelect } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

interface Props {
  /** 条件组（受控）。 */
  modelValue?: DictConditionGroup
  /** 可用字段项（固定字段 + 属性）。 */
  fields?: DictAttrFieldOption[]
  /** 最大嵌套深度（缺省 2）。 */
  maxDepth?: number
  /** 禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => ({ logic: 'AND', children: [] }),
  fields: () => [],
  maxDepth: DICT_CONDITION_MAX_DEPTH,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: DictConditionGroup]
  change: [value: DictConditionGroup]
}>()

const { value: groupValue, setValue: setGroupValue, disabled: effectiveDisabled } = useBaseInput<DictConditionGroup>({
  disabled: props.disabled,
})
setGroupValue(cloneGroup(props.modelValue))

/** 条件组（空值回落根组）。 */
const group = computed<DictConditionGroup>(() => groupValue.value ?? { logic: 'AND', children: [] })

watch(
  () => props.modelValue,
  (next) => {
    setGroupValue(cloneGroup(next))
  },
)
/** 生效禁用（件级禁用 ∨ 基类禁用）。 */
const isDisabled = computed(() => props.disabled || effectiveDisabled.value)

/**
 * 深拷贝条件组（避免直接改写受控值）。
 *
 * @param source 条件组。
 * @returns 拷贝。
 */
function cloneGroup(source: DictConditionGroup): DictConditionGroup {
  return {
    logic: source.logic,
    children: source.children.map((child) =>
      'children' in child ? cloneGroup(child) : { ...child },
    ),
  }
}

/**
 * 提交变更。
 *
 * @param next 条件组。
 */
function commit(next: DictConditionGroup): void {
  setGroupValue(next)
  emit('update:modelValue', next)
  emit('change', next)
}

/**
 * 切换组逻辑。
 *
 * @param logic 逻辑。
 */
function setLogic(logic: 'AND' | 'OR'): void {
  commit({ ...group.value, logic })
}

/**
 * 追加条件项（默认取首个字段与默认操作符）。
 */
function addItem(): void {
  const field = props.fields[0]
  if (field === undefined) {
    return
  }
  const item: DictConditionItem = { field: field.field, operator: defaultOperatorsOf(field.dataType)[0] ?? 'eq' }
  commit({ ...group.value, children: [...group.value.children, item] })
}

/**
 * 追加子组（深度受限）。
 *
 * @param parentIndex 父条件组内位置。
 */
function addGroup(): void {
  if (props.maxDepth <= 1) {
    return
  }
  commit({
    ...group.value,
    children: [...group.value.children, { logic: 'AND', children: [] }],
  })
}

/**
 * 删除条件 / 子组。
 *
 * @param index 位置。
 */
function removeChild(index: number): void {
  commit({ ...group.value, children: group.value.children.filter((_, position) => position !== index) })
}

/**
 * 更新条件项（字段联动操作符重置）。
 *
 * @param index 位置。
 * @param patch 补丁。
 */
function updateItem(index: number, patch: Partial<DictConditionItem>): void {
  const children = group.value.children.map((child, position) => {
    if (position !== index || 'children' in child) {
      return child
    }
    const next: DictConditionItem = { ...child, ...patch }
    if (patch.field !== undefined) {
      const field = fieldOf(patch.field)
      if (field !== undefined && !isOperatorAllowed(field.dataType, next.operator)) {
        next.operator = defaultOperatorsOf(field.dataType)[0] ?? 'eq'
      }
      next.value = undefined
    }
    if (patch.operator !== undefined) {
      next.value = undefined
    }
    return next
  })
  commit({ ...group.value, children })
}

/**
 * 更新子组（递归）。
 *
 * @param index 位置。
 * @param child 子组。
 */
function updateGroup(index: number, child: DictConditionGroup): void {
  const children = group.value.children.map((entry, position) => (position === index ? child : entry))
  commit({ ...group.value, children })
}

/**
 * 取字段项。
 *
 * @param field 字段名。
 */
function fieldOf(field: string): DictAttrFieldOption | undefined {
  return props.fields.find((entry) => entry.field === field)
}

/**
 * 条件项可用操作符。
 *
 * @param item 条件项。
 */
function operatorsOf(item: DictConditionItem): readonly DictOperator[] {
  const field = fieldOf(item.field)
  return field === undefined ? defaultOperatorsOf('text') : field.operators
}

/** 操作符文案。 */
function operatorText(operator: string): string {
  return DICT_OPERATOR_TEXTS[operator] ?? operator
}

/** 是否空值类操作符（无需取值）。 */
function isNullLike(operator: string): boolean {
  return operator === 'is_null' || operator === 'not_null'
}

/** 是否多值操作符（逗号分隔输入）。 */
function isListLike(operator: string): boolean {
  return operator === 'in' || operator === 'not_in'
}

/** 是否区间操作符（双值输入）。 */
function isRangeLike(operator: string): boolean {
  return operator === 'between'
}

/**
 * 值文本化（列表 / 区间 / 标量）。
 *
 * @param value 值。
 * @returns 文本。
 */
function listText(value: unknown): string {
  if (Array.isArray(value)) {
    return (value as unknown[]).map((entry) => String(entry)).join(',')
  }
  return value === undefined || value === null ? '' : String(value)
}

/**
 * 标量文本化。
 *
 * @param value 值。
 * @returns 文本。
 */
function scalarText(value: unknown): string {
  return value === undefined || value === null ? '' : String(value)
}

/**
 * 输入文本 → 条件值（列表 / 区间 / 标量）。
 *
 * @param operator 操作符。
 * @param text 输入文本。
 * @returns 条件值。
 */
function parseValue(operator: string, text: string): unknown {
  if (operator === 'in' || operator === 'not_in') {
    return text
      .split(',')
      .map((part) => part.trim())
      .filter((part) => part !== '')
  }
  if (operator === 'between') {
    const parts = text.split(',').map((part) => part.trim())
    return parts.length === 2 ? parts : text
  }
  if (text === '') {
    return undefined
  }
  const numeric = Number(text)
  return Number.isFinite(numeric) && text.trim() !== '' ? numeric : text
}

/** 条件项展示文本（摘要）。 */
const summary = computed(() => `${group.value.children.length} 个条件`)

</script>

<template>
  <div class="bms-condition-group" :data-depth="maxDepth" :data-disabled="isDisabled" data-test="condition-group">
    <div class="bms-condition-group__head">
      <el-select
        :model-value="group.logic"
        :disabled="isDisabled"
        size="small"
        style="width: 96px"
        data-test="condition-group-logic"
        @update:model-value="setLogic($event)"
      >
        <el-option label="满足全部（AND）" value="AND" />
        <el-option label="满足任一（OR）" value="OR" />
      </el-select>
      <span class="bms-condition-group__summary">{{ summary }}</span>
      <el-button size="small" :disabled="isDisabled" data-test="condition-add" @click="addItem">添加条件</el-button>
      <el-button v-if="maxDepth > 1" size="small" :disabled="isDisabled" data-test="condition-group-add" @click="addGroup">
        添加子组
      </el-button>
    </div>

    <div
      v-for="(child, index) in group.children"
      :key="index"
      class="bms-condition-group__row"
      :data-test="`condition-item-${index}`"
    >
      <template v-if="'children' in child">
        <div class="bms-condition-group__nested">
          <condition-group-builder
            :model-value="child"
            :fields="fields"
            :max-depth="maxDepth - 1"
            :disabled="isDisabled"
            @update:model-value="updateGroup(index, $event)"
          />
        </div>
      </template>
      <template v-else>
        <el-select
          :model-value="child.field"
          :disabled="isDisabled"
          size="small"
          style="width: 160px"
          @update:model-value="updateItem(index, { field: $event })"
        >
          <el-option v-for="field in fields" :key="field.field" :label="field.label" :value="field.field" />
        </el-select>
        <el-select
          :model-value="child.operator"
          :disabled="isDisabled"
          size="small"
          style="width: 120px"
          @update:model-value="updateItem(index, { operator: $event as DictOperator })"
        >
          <el-option
            v-for="operator in operatorsOf(child)"
            :key="operator"
            :label="operatorText(operator)"
            :value="operator"
          />
        </el-select>
        <el-input
          v-if="!isNullLike(child.operator)"
          :model-value="isListLike(child.operator) || isRangeLike(child.operator) ? listText(child.value) : scalarText(child.value)"
          :disabled="isDisabled"
          size="small"
          :placeholder="isRangeLike(child.operator) ? '最小值,最大值' : isListLike(child.operator) ? '多个值逗号分隔' : '值'"
          style="width: 220px"
          @update:model-value="updateItem(index, { value: parseValue(child.operator, $event) })"
        />
      </template>
      <el-button size="small" :disabled="isDisabled" :data-test="`condition-remove-${index}`" @click="removeChild(index)">
        删除
      </el-button>
    </div>
  </div>
</template>



<style scoped>
.bms-condition-group {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
  padding: var(--bms-spacing-md);
  border: 1px solid var(--bms-dict-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-dict-panel-bg);
}
.bms-condition-group__head {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
}
.bms-condition-group__summary {
  flex: 1;
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}
.bms-condition-group__row {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
}
.bms-condition-group__nested {
  flex: 1;
}
</style>
