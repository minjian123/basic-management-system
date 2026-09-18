<script setup lang="ts">
// 开关字段（06_02）：三态（undefined 未设置）+ 必填校验 + 危险切换确认（复用 `03_01`）。
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import SwitchInput from '../input/SwitchInput.vue'

interface Props {
  /** 值（受控；`undefined` 未设置）。 */
  modelValue?: boolean
  /** 必填（必须显式设置）。 */
  required?: boolean
  /** 危险切换确认（字符串为提示文案）。 */
  confirm?: boolean | string
  /** 开启文案。 */
  activeText?: string
  /** 关闭文案。 */
  inactiveText?: string
  /** 禁用。 */
  disabled?: boolean
  /** 加载态。 */
  loading?: boolean
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  required: false,
  confirm: false,
  activeText: '',
  inactiveText: '',
  disabled: false,
  loading: false,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
  invalid: [message: string]
}>()

const { value, setValue } = useBaseInput<boolean>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

const internalError = computed(() => (props.required && value.value === undefined ? '该字段为必填项' : ''))

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

function onUpdate(next: boolean): void {
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<template>
  <div class="bms-switch-field" :data-invalid="resolvedError !== ''" :data-set="value !== undefined">
    <switch-input
      class="bms-switch-field__control"
      :model-value="value"
      :disabled="disabled"
      :loading="loading"
      :confirm="confirm"
      :active-text="activeText"
      :inactive-text="inactiveText"
      :indeterminate="value === undefined"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
