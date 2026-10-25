<script setup lang="ts">
// 穿梭框（06_03）：双列表穿梭 / 搜索 / 分组 / 异步加载 / 上限；只读回显，受控经 `useBaseInput`。
// 补：取值 / 展示字段名可配 / 变化明细 / 只读顿号回显 / 失效标记 / 内容操作暴露 / 空态。
import { ElButton, ElTransfer } from 'element-plus'

import EmptyState from '../feedback/EmptyState.vue'
import { computed, onMounted, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 穿梭项。 */
export interface TransferItem {
  /** 键。 */
  key: string | number
  /** 文案。 */
  label: string
  /** 是否禁用。 */
  disabled?: boolean
  /** 分组名。 */
  group?: string
}

/** 字段值（选中键数组）。 */
export type TransferValue = (string | number)[]

interface Props {
  /** 值（受控，选中键数组）。 */
  modelValue?: TransferValue
  /** 数据（静态）。 */
  data?: TransferItem[]
  /** 异步数据加载（提供则挂载即请求）。 */
  load?: () => Promise<TransferItem[]>
  /** 标题（[左, 右]）。 */
  titles?: [string, string]
  /** 可搜索。 */
  searchable?: boolean
  /** 最多选中数。 */
  limit?: number
  /** 取值 / 展示字段名（对齐数据源；缺省 `key` / `label` / `disabled`）。 */
  fieldNames?: { key?: string; label?: string; disabled?: string }
  /** 只读（标签回显）。 */
  readonly?: boolean
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 空数据文案。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  data: () => [],
  load: undefined,
  titles: () => ['待选', '已选'],
  searchable: true,
  limit: undefined,
  fieldNames: undefined,
  readonly: false,
  required: false,
  disabled: false,
  placeholder: '暂无数据',
  errorMessage: '',
})

/** 变化明细（新增 / 移除项）。 */
export interface TransferChangeDetail {
  /** 方向。 */
  direction: 'add' | 'remove'
  /** 本次移动的键。 */
  movedKeys: TransferValue
}

const emit = defineEmits<{
  'update:modelValue': [value: TransferValue]
  change: [value: TransferValue, detail?: TransferChangeDetail]
  invalid: [message: string]
  retry: []
}>()

const { value, disabled, setValue } = useBaseInput<TransferValue>({ disabled: props.disabled })
const items = ref<TransferItem[]>(props.data)
const loadError = ref(false)
const limitError = ref('')

watch(
  () => props.modelValue,
  (next) => setValue(Array.isArray(next) ? next : []),
  { immediate: true },
)

watch(
  () => props.data,
  (next) => {
    items.value = next
  },
  { deep: true },
)

const selected = computed<TransferValue>(() => (Array.isArray(value.value) ? value.value : []))

const internalError = computed<string>(() => {
  if (loadError.value) {
    return '数据加载失败'
  }
  if (limitError.value !== '') {
    return limitError.value
  }
  if (props.required && selected.value.length === 0) {
    return '该字段为必填项'
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

/** 只读回显标签（缺标签降级为键文本）。 */
const readonlyLabels = computed<string[]>(() =>
  selected.value.map((key) => items.value.find((item) => item.key === key)?.label ?? String(key)),
)

/** 生效字段名（缺省 `key` / `label` / `disabled`）。 */
const resolvedFieldNames = computed(() => ({
  key: props.fieldNames?.key ?? 'key',
  label: props.fieldNames?.label ?? 'label',
  disabled: props.fieldNames?.disabled ?? 'disabled',
}))

/** 渲染数据（分组以「组名 · 文案」前缀呈现）。 */
const transferData = computed(() =>
  items.value.map((item) => ({
    ...item,
    label: item.group === undefined || item.group === '' ? item.label : `${item.group} · ${item.label}`,
  })),
)

/** 已选项在候选中不存在的键（已停用 / 删除 → 标记「已失效」，节点 §5/§9）。 */
const staleKeys = computed<TransferValue>(() => selected.value.filter((key) => !items.value.some((item) => item.key === key)))

/** 空态（无候选数据；节点 §4「空态」）。 */
const isEmpty = computed(() => items.value.length === 0 && props.load === undefined)

function onUpdate(next: TransferValue): void {
  const normalized = Array.isArray(next) ? next : []
  if (props.limit !== undefined && normalized.length > props.limit) {
    limitError.value = `最多选择 ${props.limit} 项`
    emit('invalid', limitError.value)
    return
  }
  limitError.value = ''
  const added = normalized.filter((key) => !selected.value.includes(key))
  const removed = selected.value.filter((key) => !normalized.includes(key))
  const detail: TransferChangeDetail | undefined =
    added.length > 0
      ? { direction: 'add', movedKeys: added }
      : removed.length > 0
        ? { direction: 'remove', movedKeys: removed }
        : undefined
  setValue(normalized)
  emit('update:modelValue', normalized)
  emit('change', normalized, detail)
}

/** 清空已选（内容操作）。 */
function clear(): void {
  setValue([])
  emit('update:modelValue', [])
  emit('change', [], { direction: 'remove', movedKeys: selected.value })
}

/** 刷新候选（内容操作）。 */
async function refresh(): Promise<void> {
  await fetchItems()
}

defineExpose({ setValue, refresh, clear })

async function fetchItems(): Promise<void> {
  if (props.load === undefined) {
    return
  }
  try {
    items.value = await props.load()
    loadError.value = false
  } catch {
    loadError.value = true
  }
}

onMounted(fetchItems)
</script>

<template>
  <div class="bms-transfer-field" :data-invalid="resolvedError !== ''">
    <div v-if="readonly" class="bms-transfer-field__readonly" data-test="transfer-readonly">
      <span v-if="readonlyLabels.length === 0">—</span>
      <span v-else>{{ readonlyLabels.join('、') }}</span>
    </div>

    <empty-state v-else-if="isEmpty" type="data" :description="placeholder" />

    <el-transfer
      v-else
      class="bms-transfer-field__control"
      :model-value="selected"
      :data="transferData"
      :titles="titles"
      :filterable="searchable"
      :disabled="disabled"
      :props="resolvedFieldNames"
      @update:model-value="onUpdate"
    />

    <p v-if="staleKeys.length > 0" class="bms-transfer-field__stale" data-test="transfer-stale">
      已失效：{{ staleKeys.join('、') }}
    </p>

    <el-button
      v-if="loadError"
      class="bms-transfer-field__retry"
      link
      size="small"
      data-test="transfer-retry"
      @click="fetchItems(); emit('retry')"
    >
      重试
    </el-button>
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-transfer-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-transfer-field__control {
  width: 100%;
}

.bms-transfer-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
  word-break: break-all;
}

.bms-transfer-field__stale {
  margin: 0;
  color: var(--bms-i18n-missing-color);
  font-size: var(--bms-font-size-xs);
}

.bms-transfer-field__retry {
  align-self: flex-start;
  font-size: var(--bms-font-size-xs);
}

@media (max-width: 992px) {
  .bms-transfer-field__control :deep(.el-transfer) {
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
