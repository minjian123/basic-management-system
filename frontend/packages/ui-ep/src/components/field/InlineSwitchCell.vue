<script setup lang="ts">
// 列表内联切换（06_02）：切换即保存（保存中禁用），失败回滚原值并发 `invalid`。
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import SwitchInput from '../input/SwitchInput.vue'

interface Props {
  /** 值（受控）。 */
  modelValue?: boolean
  /** 保存处理器（抛错 / reject 触发回滚）。 */
  save?: (value: boolean) => Promise<void>
  /** 禁用。 */
  disabled?: boolean
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  save: undefined,
  disabled: false,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
  saved: [value: boolean]
  invalid: [message: string]
}>()

const { value, setValue } = useBaseInput<boolean>({ disabled: props.disabled })
const saving = ref(false)
const saveError = ref('')

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : saveError.value))

async function onUpdate(next: boolean): Promise<void> {
  if (saving.value) {
    return
  }
  saving.value = true
  saveError.value = ''
  try {
    await props.save?.(next)
    setValue(next)
    emit('update:modelValue', next)
    emit('change', next)
    emit('saved', next)
  } catch {
    saveError.value = '保存失败，已回滚'
    emit('invalid', saveError.value)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="bms-inline-switch-cell" :data-saving="saving" :data-invalid="resolvedError !== ''">
    <switch-input
      class="bms-inline-switch-cell__control"
      :model-value="value"
      :disabled="disabled"
      :loading="saving"
      :indeterminate="value === undefined"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
