<script setup lang="ts">
// 级联选择（06_02）：多级联动 / 任意级可选 / 多选 / 搜索 / 懒加载 / 路径回显；空态经 `03_02`。
// 补：路径展示开关 / 展开触发 / 可清除 / emitPath 显式化 / 懒加载加载态 / 失败重放 / 内容操作暴露。
import { ElButton, ElCascader, type CascaderOption } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import EmptyState from '../feedback/EmptyState.vue'

/** 级联选项。 */
export interface CascadeOption {
  /** 值。 */
  value: string
  /** 文案。 */
  label: string
  /** 是否禁用。 */
  disabled?: boolean
  /** 子级。 */
  children?: CascadeOption[]
}

/** 字段值（单选路径 / 多选路径数组）。 */
export type CascadeValue = string[] | string[][] | undefined

interface Props {
  /** 值（受控）。 */
  modelValue?: CascadeValue
  /** 级联选项。 */
  options?: CascadeOption[]
  /** 多选。 */
  multiple?: boolean
  /** 任意级可选。 */
  checkStrictly?: boolean
  /** 可搜索。 */
  searchable?: boolean
  /** 懒加载。 */
  lazy?: boolean
  /** 懒加载取子级。 */
  load?: (node: CascadeOption | undefined) => Promise<CascadeOption[]>
  /** 路径展示开关（标签是否显示完整路径；缺省 `true`）。 */
  pathDisplay?: boolean
  /** 展开触发（缺省 `click`）。 */
  expandTrigger?: 'click' | 'hover'
  /** 可清除（缺省 `true`）。 */
  clearable?: boolean
  /** 值含完整路径（缺省 `true`；关闭则仅末级值）。 */
  emitPath?: boolean
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
  options: () => [],
  multiple: false,
  checkStrictly: false,
  searchable: true,
  lazy: false,
  load: undefined,
  pathDisplay: true,
  expandTrigger: 'click',
  clearable: true,
  emitPath: true,
  readonly: false,
  required: false,
  disabled: false,
  placeholder: '请选择',
  emptyText: '暂无数据',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: CascadeValue]
  change: [value: CascadeValue]
  invalid: [message: string]
  retry: []
}>()

const { value, disabled, setValue } = useBaseInput<CascadeValue>({ disabled: props.disabled })
const loadError = ref(false)
/** 懒加载中（节点 §4「加载中显示加载态」）。 */
const loading = ref(false)
/** 最近一次懒加载入参（失败重放用）。 */
let lastLoad: { node: unknown; resolve: (children: Record<string, unknown>[]) => void; reject: () => void } | undefined

watch(
  () => props.modelValue,
  (next) => {
    if (props.multiple) {
      const paths = Array.isArray(next) && Array.isArray(next[0]) ? (next as string[][]) : next === undefined ? [] : [next as string[]]
      setValue(paths as CascadeValue)
      return
    }
    const single = Array.isArray(next) && Array.isArray(next[0]) ? (next as string[][])[0] : (next as string[] | undefined)
    setValue(single)
  },
  { immediate: true },
)

/** 选项路径文本映射（本地模式）。 */
const pathMap = computed(() => {
  const map = new Map<string, string>()
  const walk = (nodes: readonly CascadeOption[], trail: string[]): void => {
    for (const node of nodes) {
      const next = [...trail, node.label]
      map.set(node.value, next.join(' / '))
      if (node.children !== undefined) {
        walk(node.children, next)
      }
    }
  }
  walk(props.options, [])
  return map
})

const paths = computed<string[][]>(() => {
  const current = value.value
  if (current === undefined) {
    return []
  }
  return Array.isArray(current[0]) ? (current as string[][]) : [current as string[]]
})

/** 只读回显。 */
const readonlyPaths = computed<string[]>(() =>
  paths.value.map((path) => path.map((segment) => pathMap.value.get(segment) ?? segment).join(' / ')),
)

const isEmpty = computed(() => !props.lazy && props.options.length === 0)

/** 级联选项（对齐 `el-cascader` 类型）。 */
const cascaderOptions = computed<CascaderOption[]>(() => props.options as unknown as CascaderOption[])

const internalError = computed<string>(() => {
  if (loadError.value) {
    return '级联数据加载失败'
  }
  const current = paths.value
  if (current.length === 0) {
    return props.required ? '该字段为必填项' : ''
  }
  if (!props.lazy && pathMap.value.size > 0) {
    const missing = current.some((path) => path.some((segment) => !pathMap.value.has(segment)))
    if (missing) {
      return '选项不在级联中'
    }
  }
  return ''
})

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : internalError.value))

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
 * 懒加载回调（对齐 `el-cascader` 的 `load` 口径）。
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
    .load?.(node as CascadeOption)
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

/** 重试：**重放请求**（经 `onLoad` 再派发一次 `retry`，与既有口径一致；节点 §5「懒加载失败可重试」）。 */
function onRetry(): void {
  if (lastLoad !== undefined) {
    onLoad(lastLoad.node, lastLoad.resolve, lastLoad.reject)
  }
}

/** 清空（内容操作）。 */
function clear(): void {
  setValue(undefined)
  emit('update:modelValue', undefined)
  emit('change', undefined)
}

/** 当前已选节点（内容操作）。 */
function selectedNodes(): string[][] {
  return paths.value
}

defineExpose({ setValue, clear, selectedNodes })

function onUpdate(next: unknown): void {
  const normalized = next as CascadeValue
  setValue(normalized)
  emit('update:modelValue', normalized)
  emit('change', normalized)
}
</script>

<template>
  <div class="bms-cascade-field" :data-invalid="resolvedError !== ''" :data-loading="loading">
    <div v-if="readonly" class="bms-cascade-field__readonly" data-test="cascade-readonly">
      <span v-for="(path, index) in readonlyPaths" :key="index" class="bms-cascade-field__path">{{ path }}</span>
      <span v-if="readonlyPaths.length === 0">—</span>
    </div>

    <empty-state v-else-if="isEmpty" type="data" :description="emptyText" />

    <el-cascader
      v-else
      class="bms-cascade-field__control"
      :model-value="value"
      :options="cascaderOptions"
      :props="{
        multiple,
        checkStrictly,
        lazy,
        lazyLoad: lazy ? onLoad : undefined,
        label: 'label',
        value: 'value',
        children: 'children',
        disabled: 'disabled',
        emitPath,
        expandTrigger,
      }"
      :show-all-levels="pathDisplay"
      :filterable="searchable"
      :clearable="clearable"
      :disabled="disabled"
      :placeholder="placeholder"
      @update:model-value="onUpdate"
    />

    <el-button
      v-if="loadError"
      class="bms-cascade-field__retry"
      link
      size="small"
      data-test="cascade-retry"
      @click="onRetry"
    >
      重试
    </el-button>
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-cascade-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-cascade-field__control {
  width: 100%;
}

.bms-cascade-field__readonly {
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

.bms-cascade-field__path {
  display: inline-flex;
  align-items: center;
  padding: 0 var(--bms-space-1);
  background: var(--bms-field-suggest-hover-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-cascade-field__retry {
  align-self: flex-start;
  font-size: var(--bms-font-size-xs);
}
</style>
