<script setup lang="ts">
// 字典级联字段（06_06）：树形多级字典（`parent_id` 构建）、任意级可选、多选、只读路径回显；编辑态复用级联件。
import { DICT_EMPTY_TEXT, DICT_PLACEHOLDER_TEXT, toDictTreeNodes, type DictItem, type DictSourceAdapter } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseDictSelect } from '../../composables/useBaseDictSelect'
import EmptyState from '../feedback/EmptyState.vue'
import CascadeField, { type CascadeValue } from './CascadeField.vue'

/** 字段值类型（单选路径 / 多选路径数组）。 */
export type DictCascadeValue = string[] | string[][] | undefined

interface Props {
  /** 值（受控）。 */
  modelValue?: DictCascadeValue
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 字典类型码。 */
  dictType?: string
  /** 字典数据源（未注入即占位零请求）。 */
  source?: DictSourceAdapter
  /** 多选。 */
  multiple?: boolean
  /** 任意级可选。 */
  checkStrictly?: boolean
  /** 可搜索。 */
  searchable?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读（路径回显）。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 空态文案。 */
  emptyText?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: false,
  dictType: '',
  source: undefined,
  multiple: false,
  checkStrictly: true,
  searchable: true,
  disabled: false,
  readonly: false,
  placeholder: '请选择',
  degradeText: DICT_PLACEHOLDER_TEXT,
  emptyText: DICT_EMPTY_TEXT,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: DictCascadeValue]
  change: [value: DictCascadeValue]
  retry: []
  invalid: [message: string]
}>()

const api = useBaseDictSelect({
  ready: props.ready,
  dictType: props.dictType,
  source: props.source,
  multiple: props.multiple,
  disabled: props.disabled,
})

const loaded = ref(false)

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.dictType,
  async (next) => {
    api.setDictType(next)
    loaded.value = false
    if (next !== '' && props.ready) {
      await loadTree()
    }
  },
  { immediate: true },
)
watch(
  () => props.multiple,
  (next) => api.setMultiple(next),
)

/**
 * 加载树数据（一次性；缓存命中不请求）。
 *
 * @returns 无。
 */
async function loadTree(): Promise<void> {
  await api.load()
  loaded.value = true
}

/** 树节点（`parent_id` 构建；停用节点禁用；结构兼容级联件选项）。 */
const treeOptions = computed(() => toDictTreeNodes(api.items.value))

/** 路径文本映射（只读回显；逐段取 label）。 */
const pathMap = computed(() => {
  const map = new Map<string, string>()
  for (const item of api.items.value as DictItem[]) {
    map.set(item.value, item.label)
  }
  return map
})

/** 只读路径回显（逐级解析；未命中回退值）。 */
const readonlyPaths = computed<string[]>(() => {
  const current = props.modelValue
  if (current === undefined || current.length === 0) {
    return []
  }
  const paths = Array.isArray(current[0]) ? (current as string[][]) : [current as string[]]
  return paths.map((path) => path.map((segment) => pathMap.value.get(segment) ?? segment).join(' / '))
})

const isEmpty = computed(() => loaded.value && api.items.value.length === 0)

watch(
  () => props.modelValue,
  (next) => {
    const values = next === undefined ? [] : Array.isArray(next[0]) ? (next as string[][]).flat() : (next as string[])
    api.setValue(values)
  },
  { immediate: true },
)

api.onValueChange(() => {
  const paths = collectPaths()
  emit('update:modelValue', paths)
  emit('change', paths)
})

/** 核心值 → 级联路径值（多选数组 / 单选路径）。 */
function collectPaths(): DictCascadeValue {
  const values = api.selectedValues.value
  if (values.length === 0) {
    return undefined
  }
  return props.multiple ? values.map((value) => [value]) : [values[0] as string]
}

/**
 * 级联件值变更 → 核心值。
 *
 * @param next 级联值。
 */
function onCascadeUpdate(next: CascadeValue): void {
  const paths = next === undefined ? [] : Array.isArray(next[0]) ? (next as string[][]) : [next as string[]]
  api.setValue(paths.map((path) => path[path.length - 1] as string))
}
</script>

<template>
  <div
    class="bms-dict-cascader-field"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <div v-else-if="readonly" class="bms-dict-cascader-field__readonly" data-test="dict-cascader-readonly">
      <span v-for="(path, index) in readonlyPaths" :key="index" class="bms-dict-cascader-field__path">{{ path }}</span>
      <span v-if="readonlyPaths.length === 0">—</span>
    </div>

    <empty-state v-else-if="isEmpty" type="data" :description="emptyText" />

    <cascade-field
      v-else
      :model-value="modelValue"
      :options="treeOptions"
      :multiple="multiple"
      :check-strictly="checkStrictly"
      :searchable="searchable"
      :disabled="disabled"
      :placeholder="placeholder"
      :empty-text="emptyText"
      :error-message="errorMessage"
      data-test="dict-cascader-field"
      @update:model-value="onCascadeUpdate"
      @change="onCascadeUpdate"
      @retry="emit('retry')"
      @invalid="emit('invalid', $event)"
    />
  </div>
</template>

<style scoped>
.bms-dict-cascader-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-dict-cascader-field__readonly {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  color: var(--bms-color-text);
}
.bms-dict-cascader-field__path {
  padding: 0 var(--bms-spacing-sm);
  background: var(--bms-dict-tag-bg);
  border: 1px solid var(--bms-dict-border);
  border-radius: var(--bms-radius-sm);
}
</style>
