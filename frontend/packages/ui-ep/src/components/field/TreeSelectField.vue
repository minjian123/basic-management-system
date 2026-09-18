<script setup lang="ts">
// 树选择字段（06_02）：单选 / 多选（父子联动策略）/ 懒加载 / 搜索 / 只读路径回显；空态经 `03_02`。
import { ElTreeSelect } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import EmptyState from '../feedback/EmptyState.vue'

/** 树节点。 */
export interface TreeFieldNode {
  /** 节点键。 */
  key: string
  /** 文案。 */
  label: string
  /** 是否禁用。 */
  disabled?: boolean
  /** 子节点。 */
  children?: TreeFieldNode[]
}

/** 字段值。 */
export type TreeFieldValue = string | string[] | undefined

interface Props {
  /** 值（受控；多选为数组）。 */
  modelValue?: TreeFieldValue
  /** 树数据（本地模式）。 */
  data?: TreeFieldNode[]
  /** 多选。 */
  multiple?: boolean
  /** 独立勾选（不父子联动）。 */
  checkStrictly?: boolean
  /** 可搜索。 */
  searchable?: boolean
  /** 懒加载。 */
  lazy?: boolean
  /** 懒加载取子节点。 */
  load?: (node: TreeFieldNode | undefined) => Promise<TreeFieldNode[]>
  /** 只读（路径回显）。 */
  readonly?: boolean
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 空态文案。 */
  emptyText?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  data: () => [],
  multiple: false,
  checkStrictly: false,
  searchable: true,
  lazy: false,
  load: undefined,
  readonly: false,
  required: false,
  disabled: false,
  placeholder: '请选择',
  emptyText: '暂无数据',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: TreeFieldValue]
  change: [value: TreeFieldValue]
  invalid: [message: string]
  retry: []
}>()

const { value, disabled, setValue } = useBaseInput<TreeFieldValue>({ disabled: props.disabled })
const loadError = ref(false)

watch(
  () => props.modelValue,
  (next) => {
    const normalized = props.multiple
      ? Array.isArray(next)
        ? next
        : next === undefined
          ? []
          : [next]
      : Array.isArray(next)
        ? next[0]
        : next
    setValue(normalized as TreeFieldValue)
  },
  { immediate: true },
)

/** 树中合法键集合（本地模式）。 */
const treeKeys = computed(() => {
  const keys = new Set<string>()
  const walk = (nodes: readonly TreeFieldNode[]): void => {
    for (const node of nodes) {
      keys.add(node.key)
      if (node.children !== undefined) {
        walk(node.children)
      }
    }
  }
  walk(props.data)
  return keys
})

/** 只读回显路径。 */
const readonlyPaths = computed<string[]>(() => {
  const selected = Array.isArray(value.value) ? value.value : value.value === undefined ? [] : [value.value]
  const findPath = (nodes: readonly TreeFieldNode[], key: string, trail: string[]): string[] | undefined => {
    for (const node of nodes) {
      const next = [...trail, node.label]
      if (node.key === key) {
        return next
      }
      if (node.children !== undefined) {
        const found = findPath(node.children, key, next)
        if (found !== undefined) {
          return found
        }
      }
    }
    return undefined
  }
  return selected.map((key) => (findPath(props.data, key, []) ?? [key]).join(' / '))
})

const internalError = computed<string>(() => {
  const current = value.value
  if (loadError.value) {
    return '树数据加载失败'
  }
  const empty = current === undefined || (Array.isArray(current) && current.length === 0)
  if (empty) {
    return props.required ? '该字段为必填项' : ''
  }
  if (!props.lazy && treeKeys.value.size > 0) {
    const selected = Array.isArray(current) ? current : [current as string]
    if (selected.some((key) => !treeKeys.value.has(key))) {
      return '选项不在树中'
    }
  }
  return ''
})

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : internalError.value))
const isEmpty = computed(() => !props.lazy && props.data.length === 0)

watch(
  internalError,
  (message) => {
    if (message !== '') {
      emit('invalid', message)
    }
  },
  { immediate: true },
)

/**
 * 懒加载回调（对齐 `el-tree-select` 的 `LoadFunction`）。
 *
 * @param node 当前节点。
 * @param resolve 成功回调。
 * @param reject 失败回调。
 */
function onLoad(node: unknown, resolve: (children: Record<string, unknown>[]) => void, reject: () => void): void {
  emit('retry')
  props
    .load?.(node as TreeFieldNode)
    .then((children) => {
      loadError.value = false
      resolve(children as unknown as Record<string, unknown>[])
    })
    .catch(() => {
      loadError.value = true
      reject()
    })
}

function onUpdate(next: TreeFieldValue): void {
  setValue(next)
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<template>
  <div class="bms-tree-select-field" :data-invalid="resolvedError !== ''">
    <div v-if="readonly" class="bms-tree-select-field__readonly" data-test="tree-readonly">
      <span v-for="(path, index) in readonlyPaths" :key="index" class="bms-tree-select-field__path">{{ path }}</span>
      <span v-if="readonlyPaths.length === 0">—</span>
    </div>

    <empty-state v-else-if="isEmpty" type="data" :description="emptyText" />

    <el-tree-select
      v-else
      class="bms-tree-select-field__control"
      :model-value="multiple ? (Array.isArray(value) ? value : []) : value"
      :data="data"
      :multiple="multiple"
      :check-strictly="checkStrictly"
      :filterable="searchable"
      :lazy="lazy"
      :load="onLoad"
      :disabled="disabled"
      :placeholder="placeholder"
      :node-key="'key'"
      :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
      @update:model-value="onUpdate"
    />

    <button v-if="loadError" type="button" data-test="tree-retry" class="bms-tree-select-field__retry" @click="emit('retry')">
      重试
    </button>
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
