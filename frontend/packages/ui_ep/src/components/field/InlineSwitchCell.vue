<script setup lang="ts">
// 列表内联切换（06_02）：乐观值（切换即按目标态展示）+ 保存中禁用 + 失败回滚原值并发 `invalid`
// + 危险开关二次确认 + 紧凑尺寸 + 乐观锁版本冲突分支（派发 `refresh` 由宿主刷新该行）。
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import { useConfirm } from '../../composables/useConfirm'
import TriStateSwitch, { type TriStateSize } from '../input/TriStateSwitch.vue'

interface Props {
  /** 值（受控）。 */
  modelValue?: boolean
  /** 保存处理器（抛错 / reject 触发回滚）。 */
  save?: (value: boolean) => Promise<void>
  /** 危险开关二次确认（字符串为提示文案）。 */
  confirm?: boolean | string
  /** 尺寸档位（表格内用紧凑）。 */
  size?: TriStateSize
  /** 禁用。 */
  disabled?: boolean
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  save: undefined,
  confirm: false,
  size: 'compact',
  disabled: false,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
  saved: [value: boolean]
  invalid: [message: string]
  /** 乐观锁版本冲突（宿主据此刷新该行）。 */
  refresh: []
  /** 确认被取消。 */
  cancel: []
}>()

const { confirm: askConfirm } = useConfirm()
const { value, setValue } = useBaseInput<boolean>({ disabled: props.disabled })
const saving = ref(false)
const saveError = ref('')
/** 乐观值（保存期间展示目标态；失败回滚）。 */
const optimistic = ref<boolean | undefined>(undefined)

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

/** 生效展示值（保存期间取乐观值，其余取受控值）。 */
const shown = computed(() => (saving.value && optimistic.value !== undefined ? optimistic.value : value.value))

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : saveError.value))

/**
 * 切换处理：二次确认 → 乐观展示 → 保存 → 成功确认值 / 失败回滚。
 *
 * @param next 目标值。
 */
async function onUpdate(next: boolean): Promise<void> {
  if (saving.value) {
    return
  }
  if (props.confirm !== false) {
    const content = typeof props.confirm === 'string' ? props.confirm : '确认切换该状态？'
    const confirmed = await askConfirm({ content, danger: true })
    if (!confirmed) {
      emit('cancel')
      return
    }
  }

  const original = value.value
  saving.value = true
  saveError.value = ''
  // 乐观：先按切换后状态展示（节点 §5）。
  optimistic.value = next
  try {
    await props.save?.(next)
    setValue(next)
    emit('update:modelValue', next)
    emit('change', next)
    emit('saved', next)
  } catch (error) {
    // 失败：回滚为原值；版本冲突单独提示并请求宿主刷新该行（节点 §5「乐观锁」）。
    optimistic.value = undefined
    const conflict = error instanceof Error && /conflict|version|409/i.test(error.message)
    saveError.value = conflict ? '数据已被他人修改' : '保存失败，已回滚'
    emit('invalid', saveError.value)
    // 确保受控值回到原值。
    setValue(original)
    if (conflict) {
      emit('refresh')
    }
  } finally {
    saving.value = false
    optimistic.value = undefined
  }
}
</script>

<template>
  <div class="bms-inline-switch-cell" :data-saving="saving" :data-invalid="resolvedError !== ''" :data-size="size">
    <tri-state-switch
      class="bms-inline-switch-cell__control"
      :model-value="shown"
      :disabled="disabled"
      :loading="saving"
      :size="size"
      :indeterminate-text="'—'"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-inline-switch-cell {
  display: inline-flex;
  flex-direction: column;
  gap: var(--bms-space-1);
}

.bms-inline-switch-cell__control {
  justify-content: center;
}
</style>
