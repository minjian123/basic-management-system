<script setup lang="ts">
// 树选择字段（06_02）：单选 / 多选（父子联动策略）/ 懒加载 / 搜索 / 只读路径回显；空态经 `03_02`。
// 补：仅叶子可选 / 排除节点含子树 / 父子独立缺省 / 多选折叠回显 / 节点点击事件 / 失败重放。
import { ElButton, ElTreeSelect } from 'element-plus'
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
  /** 仅叶子可选（非叶子节点不可选、点击只展开）。 */
  onlyLeaf?: boolean
  /** 排除节点（含子树），选上级时排除自身防环。 */
  excludeSubtree?: string[]
  /** 多选折叠回显（超过阈值折叠为「标签1 等 M 项」；缺省开启）。 */
  collapseTags?: boolean
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
  checkStrictly: true,
  searchable: true,
  onlyLeaf: false,
  excludeSubtree: () => [],
  collapseTags: true,
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
  /** 节点点击（联动其他字段；节点 §4「值变化通知含节点点击」）。 */
  'node-click': [key: string]
}>()

const { value, disabled, setValue } = useBaseInput<TreeFieldValue>({ disabled: props.disabled })
const loadError = ref(false)
/** 懒加载中。 */
const loading = ref(false)
/** 最近一次懒加载入参（失败重放用）。 */
let lastLoad: { node: unknown; resolve: (children: Record<string, unknown>[]) => void; reject: () => void } | undefined

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

/** 排除节点集合（含子树）。 */
const excludedKeys = computed<Set<string>>(() => {
  const excluded = new Set<string>()
  const collect = (nodes: readonly TreeFieldNode[], trail: string[]): void => {
    for (const node of nodes) {
      if (props.excludeSubtree.includes(node.key)) {
        const gather = (target: TreeFieldNode): void => {
          excluded.add(target.key)
          target.children?.forEach(gather)
        }
        gather(node)
        continue
      }
      trail.push(node.key)
      if (node.children !== undefined) {
        collect(node.children, trail)
      }
    }
  }
  collect(props.data, [])
  return excluded
})

/** 生效树数据（剔除排除节点及其子树；仅叶子时标记非叶子不可选）。 */
const effectiveData = computed<TreeFieldNode[]>(() => {
  const map = (nodes: readonly TreeFieldNode[]): TreeFieldNode[] =>
    nodes
      .filter((node) => !excludedKeys.value.has(node.key))
      .map((node) => ({
        ...node,
        disabled: node.disabled === true || (props.onlyLeaf && (node.children?.length ?? 0) > 0),
        children: node.children === undefined ? undefined : map(node.children),
      }))
  return map(props.data)
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
  lastLoad = { node, resolve, reject }
  emit('retry')
  loading.value = true
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
    .finally(() => {
      loading.value = false
    })
}

/** 重试：**重放请求**（经 `onLoad` 再派发一次 `retry`，与既有口径一致）。 */
function onRetry(): void {
  if (lastLoad !== undefined) {
    onLoad(lastLoad.node, lastLoad.resolve, lastLoad.reject)
  }
}

/** 节点点击（节点 §4）。 */
function onNodeClick(node: unknown): void {
  const key = (node as TreeFieldNode | undefined)?.key
  if (key !== undefined) {
    emit('node-click', key)
  }
}

/** 清空（内容操作）。 */
function clear(): void {
  setValue(undefined)
  emit('update:modelValue', undefined)
  emit('change', undefined)
}

defineExpose({ setValue, clear })

function onUpdate(next: TreeFieldValue): void {
  setValue(next)
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<template>
  <div class="bms-tree-select-field" :data-invalid="resolvedError !== ''" :data-loading="loading">
    <div v-if="readonly" class="bms-tree-select-field__readonly" data-test="tree-readonly">
      <span v-for="(path, index) in readonlyPaths" :key="index" class="bms-tree-select-field__path">{{ path }}</span>
      <span v-if="readonlyPaths.length === 0">—</span>
    </div>

    <empty-state v-else-if="isEmpty" type="data" :description="emptyText" />

    <el-tree-select
      v-else
      class="bms-tree-select-field__control"
      :model-value="multiple ? (Array.isArray(value) ? value : []) : value"
      :data="effectiveData"
      :multiple="multiple"
      :check-strictly="checkStrictly"
      :filterable="searchable"
      :lazy="lazy"
      :load="onLoad"
      :disabled="disabled"
      :placeholder="placeholder"
      :node-key="'key'"
      :collapse-tags="collapseTags"
      :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
      @update:model-value="onUpdate"
      @node-click="onNodeClick"
    />

    <el-button
      v-if="loadError"
      class="bms-tree-select-field__retry"
      link
      size="small"
      data-test="tree-retry"
      @click="onRetry"
    >
      重试
    </el-button>
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-tree-select-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-tree-select-field__control {
  width: 100%;
}

.bms-tree-select-field__readonly {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-1);
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}

.bms-tree-select-field__path {
  display: inline-flex;
  align-items: center;
  padding: 0 var(--bms-space-1);
  background: var(--bms-field-suggest-hover-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-tree-select-field__retry {
  align-self: flex-start;
  font-size: var(--bms-font-size-xs);
}
</style>
