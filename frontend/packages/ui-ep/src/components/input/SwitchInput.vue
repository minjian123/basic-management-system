<script setup lang="ts">
// 开关：布尔（三态未设置 / 加载态 / 危险切换确认），受控经 `useBaseInput`；确认复用 `03_01`。
import { ElSwitch } from 'element-plus'
import { watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import { useConfirm } from '../../composables/useConfirm'

interface Props {
  /** 值（受控；`undefined` 表示未设置）。 */
  modelValue?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 加载态。 */
  loading?: boolean
  /** 危险切换确认（字符串为提示文案）。 */
  confirm?: boolean | string
  /** 开启文案。 */
  activeText?: string
  /** 关闭文案。 */
  inactiveText?: string
  /** 未设置态展示。 */
  indeterminate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  disabled: false,
  loading: false,
  confirm: false,
  activeText: '',
  inactiveText: '',
  indeterminate: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
}>()

const { confirm: askConfirm } = useConfirm()
const { value, disabled, setValue, onValueChange, setLoading } = useBaseInput<boolean>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

watch(
  () => props.loading,
  (next) => {
    setLoading(next)
  },
  { immediate: true },
)

onValueChange((next) => {
  const normalized = next === true
  emit('update:modelValue', normalized)
  emit('change', normalized)
})

async function onUpdate(next: string | number | boolean): Promise<void> {
  if (props.confirm !== false) {
    const content = typeof props.confirm === 'string' ? props.confirm : '该操作会影响当前数据，确定切换吗？'
    const confirmed = await askConfirm({ content, danger: true })
    if (!confirmed) {
      return
    }
  }
  setValue(next === true)
}
</script>

<template>
  <el-switch
    class="bms-switch-input"
    :model-value="value"
    :disabled="disabled"
    :loading="loading"
    :active-text="activeText"
    :inactive-text="inactiveText"
    :indeterminate="indeterminate"
    @update:model-value="onUpdate"
  />
</template>
