<script setup lang="ts">
// 三态开关件（11_03 新增）：未设置（`undefined`）/ 开 / 关 三态。
// Element Plus `el-switch` 无 `indeterminate`（2.14.7 实测），无法承载「未设置」态，
// 故自绘实现；契约对齐《组件设计 · 开关与枚举字段》§4（受控值与三态 / 文案变体 / 加载态 / 尺寸档位）。
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 尺寸档位。 */
export type TriStateSize = 'default' | 'compact'

interface Props {
  /** 值（受控；`undefined` 表示未设置）。 */
  modelValue?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 加载态。 */
  loading?: boolean
  /** 开启文案。 */
  activeText?: string
  /** 关闭文案。 */
  inactiveText?: string
  /** 未设置文案。 */
  indeterminateText?: string
  /** 尺寸档位（表格内用紧凑）。 */
  size?: TriStateSize
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  disabled: false,
  loading: false,
  activeText: '',
  inactiveText: '',
  indeterminateText: '—',
  size: 'default',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
}>()

const { value, disabled, setValue, setLoading } = useBaseInput<boolean>({ disabled: props.disabled })

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

/** 三态标识（供样式与可访问性使用）。 */
const state = computed<'unset' | 'on' | 'off'>(() => (value.value === undefined ? 'unset' : value.value ? 'on' : 'off'))

/** `aria-checked` 三态（`mixed` 表示未设置）。 */
const ariaChecked = computed(() => (value.value === undefined ? 'mixed' : value.value ? 'true' : 'false'))

/** 当前展示文案（未设置走 `indeterminateText`）。 */
const label = computed(() => {
  if (state.value === 'unset') {
    return props.indeterminateText
  }
  return state.value === 'on' ? props.activeText : props.inactiveText
})

/**
 * 切换三态：未设置 → 开 → 关 → 开（未设置仅在初始出现，切换后进入布尔二态）。
 */
function onToggle(): void {
  if (disabled.value || props.loading) {
    return
  }
  // 仅在**用户交互**时上抛：受控 prop 同步（`watch` → `setValue`）不回抛，
  // 否则消费方的状态机（如 `InlineSwitchCell` 的保存流程）会被自身回显重复触发。
  const next = value.value !== true
  setValue(next)
  emit('update:modelValue', next)
  emit('change', next)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    onToggle()
  }
}
</script>

<template>
  <div class="bms-tri-state-switch" :data-state="state" :data-size="size" :data-loading="loading">
    <button
      type="button"
      class="bms-tri-state-switch__track"
      role="switch"
      data-test="tri-state-switch"
      :aria-checked="ariaChecked"
      :aria-disabled="disabled"
      :disabled="disabled"
      @click="onToggle"
      @keydown="onKeydown"
    >
      <span class="bms-tri-state-switch__thumb" />
    </button>
    <span v-if="label !== ''" class="bms-tri-state-switch__label">{{ label }}</span>
  </div>
</template>

<style scoped>
.bms-tri-state-switch {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-2);
  font-size: var(--bms-font-size);
}

.bms-tri-state-switch__track {
  position: relative;
  flex: none;
  width: 40px;
  height: 20px;
  padding: 0;
  background: var(--bms-tristate-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.bms-tri-state-switch__track:focus-visible {
  outline: 2px solid var(--bms-color-primary);
  outline-offset: 1px;
}

.bms-tri-state-switch__thumb {
  position: absolute;
  top: 1px;
  left: 1px;
  width: 16px;
  height: 16px;
  background: var(--bms-color-bg);
  border-radius: 50%;
  box-shadow: var(--bms-shadow-1);
  transition: left 0.2s;
}

.bms-tri-state-switch[data-state='on'] .bms-tri-state-switch__track {
  background: var(--bms-color-primary);
  border-color: var(--bms-color-primary);
}

.bms-tri-state-switch[data-state='on'] .bms-tri-state-switch__thumb {
  left: 21px;
}

.bms-tri-state-switch[data-state='unset'] .bms-tri-state-switch__track {
  background: var(--bms-tristate-bg);
  border-style: dashed;
}

.bms-tri-state-switch[data-state='unset'] .bms-tri-state-switch__label {
  color: var(--bms-tristate-color);
}

.bms-tri-state-switch__label {
  color: var(--bms-color-text);
  line-height: var(--bms-line-height);
}

.bms-tri-state-switch__track:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-tri-state-switch[data-size='compact'] .bms-tri-state-switch__track {
  width: 32px;
  height: 16px;
  border-radius: 8px;
}

.bms-tri-state-switch[data-size='compact'] .bms-tri-state-switch__thumb {
  width: 12px;
  height: 12px;
}

.bms-tri-state-switch[data-size='compact'][data-state='on'] .bms-tri-state-switch__thumb {
  left: 17px;
}

.bms-tri-state-switch[data-size='compact'] .bms-tri-state-switch__label {
  font-size: var(--bms-font-size-xs);
}

.bms-tri-state-switch[data-loading='true'] .bms-tri-state-switch__track {
  cursor: progress;
}
</style>
