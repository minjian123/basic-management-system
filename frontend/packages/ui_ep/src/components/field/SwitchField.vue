<script setup lang="ts">
// 开关字段（06_02）：三态（undefined 未设置）+ 必填校验 + 危险切换确认（复用 `03_01`）
// + 尺寸档位 + 切换前置判定 + 三态清空入口 + 只读回显。
//
// 三态承载改用自绘 `TriStateSwitch`：Element Plus `el-switch` 无 `indeterminate`（2.14.7 实测），
// 无法呈现节点 §4 要求的「未设置」态。
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import { useConfirm } from '../../composables/useConfirm'
import TriStateSwitch, { type TriStateSize } from '../input/TriStateSwitch.vue'

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
  /** 未设置文案。 */
  indeterminateText?: string
  /** 尺寸档位（表格内用紧凑）。 */
  size?: TriStateSize
  /** 切换前置判定（返回 `false` 撤销切换）。 */
  beforeChange?: (value: boolean) => boolean | Promise<boolean>
  /** 可清空（三态清空入口）。 */
  clearable?: boolean
  /** 只读（纯文本回显）。 */
  readonly?: boolean
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
  indeterminateText: '—',
  size: 'default',
  beforeChange: undefined,
  clearable: false,
  readonly: false,
  disabled: false,
  loading: false,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
  invalid: [message: string]
  /** 确认被取消（供页面统计 / 提示）。 */
  cancel: []
  /** 清空为未设置态。 */
  clear: []
}>()

const { confirm: askConfirm } = useConfirm()
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

/** 只读回显文本（无文案按「是 / 否」；未设置占位 `—`——节点 §8）。 */
const readonlyText = computed(() => {
  if (value.value === undefined) {
    return props.indeterminateText
  }
  if (value.value) {
    return props.activeText === '' ? '是' : props.activeText
  }
  return props.inactiveText === '' ? '否' : props.inactiveText
})

/**
 * 切换处理：前置判定 → 危险确认 → 写值（节点 §4：确认前不改变受控值）。
 *
 * @param next 目标值。
 */
async function onUpdate(next: boolean): Promise<void> {
  if (props.beforeChange !== undefined) {
    const allowed = await props.beforeChange(next)
    if (!allowed) {
      return
    }
  }
  if (props.confirm !== false) {
    const content = typeof props.confirm === 'string' ? props.confirm : '该操作会影响当前数据，确定切换吗？'
    const confirmed = await askConfirm({ content, danger: true })
    if (!confirmed) {
      emit('cancel')
      return
    }
  }
  setValue(next)
  emit('update:modelValue', next)
  emit('change', next)
}

/** 清空为未设置态（三态清空入口）。 */
function onClear(): void {
  setValue(undefined)
  emit('clear')
}
</script>

<template>
  <div
    class="bms-switch-field"
    :data-invalid="resolvedError !== ''"
    :data-set="value !== undefined"
    :data-size="size"
  >
    <div v-if="readonly" class="bms-switch-field__readonly" data-test="switch-readonly">{{ readonlyText }}</div>

    <div v-else class="bms-switch-field__control">
      <tri-state-switch
        :model-value="value"
        :disabled="disabled"
        :loading="loading"
        :size="size"
        :active-text="activeText"
        :inactive-text="inactiveText"
        :indeterminate-text="indeterminateText"
        @update:model-value="onUpdate"
      />
      <el-button
        v-if="clearable && value !== undefined"
        class="bms-switch-field__clear"
        link
        size="small"
        data-test="switch-clear"
        @click="onClear"
      >
        清除
      </el-button>
    </div>

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-switch-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-switch-field__control {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-2);
  min-height: var(--bms-control-height);
}

.bms-switch-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}

.bms-switch-field__clear {
  font-size: var(--bms-font-size-xs);
}
</style>
