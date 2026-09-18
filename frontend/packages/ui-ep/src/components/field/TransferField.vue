<script setup lang="ts">
// 穿梭框（06_03）：双列表穿梭 / 搜索 / 分组 / 异步加载 / 上限；只读回显，受控经 `useBaseInput`。
import { ElTransfer } from 'element-plus'
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
  readonly: false,
  required: false,
  disabled: false,
  placeholder: '暂无数据',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: TransferValue]
  change: [value: TransferValue]
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

/** 渲染数据（分组以「组名 · 文案」前缀呈现）。 */
const transferData = computed(() =>
  items.value.map((item) => ({
    ...item,
    label: item.group === undefined || item.group === '' ? item.label : `${item.group} · ${item.label}`,
  })),
)

function onUpdate(next: TransferValue): void {
  const normalized = Array.isArray(next) ? next : []
  if (props.limit !== undefined && normalized.length > props.limit) {
    limitError.value = `最多选择 ${props.limit} 项`
    emit('invalid', limitError.value)
    return
  }
  limitError.value = ''
  setValue(normalized)
  emit('update:modelValue', normalized)
  emit('change', normalized)
}

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
      <span v-for="(label, index) in readonlyLabels" :key="index" class="bms-transfer-field__tag">{{ label }}</span>
      <span v-if="readonlyLabels.length === 0">—</span>
    </div>

    <el-transfer
      v-else
      class="bms-transfer-field__control"
      :model-value="selected"
      :data="transferData"
      :titles="titles"
      :filterable="searchable"
      :disabled="disabled"
      :props="{ key: 'key', label: 'label', disabled: 'disabled' }"
      @update:model-value="onUpdate"
    />

    <button v-if="loadError" type="button" data-test="transfer-retry" class="bms-transfer-field__retry" @click="fetchItems(); emit('retry')">
      重试
    </button>
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
