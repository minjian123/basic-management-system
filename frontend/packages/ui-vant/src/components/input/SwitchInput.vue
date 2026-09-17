<script setup lang="ts">
/**
 * 开关（移动端 / Vant 侧）：布尔开关原语（《组件设计 · 开关》，与 `ui-ep` 同契约）。
 *
 * 值域前端只暴露 `boolean | null`（后端 `SMALLINT` 1/0 经核心 `normalizeBooleanValue` 归一）；
 * `threeState` 区分「未设置（`null`）」与「关（`false`）」；`dangerConfirm` 走插件确认注入点
 * （`ui-vant/src/confirm.ts` → `showConfirmDialog`，宿主可覆盖）。
 */

import { normalizeBooleanValue } from '@bms/core'

import { Switch as VanSwitch } from 'vant/es/switch'
import 'vant/es/switch/style'

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useComponentBase } from '@bms/vue'

import { confirm } from '../../confirm'
import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

interface ShellExpose {
  setValue(value: unknown): void
  clear(): void
  commit(): unknown
}

const props = withDefaults(
  defineProps<{
    /** 受控值（接受后端 `SMALLINT` 1/0 与布尔字面量；对外只发布尔 / `null`） */
    modelValue?: boolean | number | string | null
    activeText?: string
    inactiveText?: string
    loading?: boolean
    dangerConfirm?: string
    threeState?: boolean
    allowClear?: boolean
    disabled?: boolean
    readonly?: boolean
    readonlyMode?: 'text' | 'disabled'
    label?: string
    required?: boolean
    help?: string
    error?: string
    size?: 'small' | 'default' | 'large'
    density?: 'default' | 'compact'
    span?: number
    fieldKey?: string
  }>(),
  {
    modelValue: null,
    activeText: '',
    inactiveText: '',
    loading: false,
    dangerConfirm: '',
    threeState: false,
    allowClear: false,
    disabled: false,
    readonly: false,
    readonlyMode: 'text',
    label: '',
    required: false,
    help: '',
    error: '',
    size: 'default',
    density: 'default',
    span: 24,
    fieldKey: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean | null]
  change: [value: boolean | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'switch-input' })
const { t } = useI18n()

const shellRef = ref<ShellExpose | null>(null)
const current = ref<boolean | null>(normalizeBooleanValue(props.modelValue))
watch(
  () => props.modelValue,
  (next) => {
    current.value = normalizeBooleanValue(next)
  },
)

const activeLabel = computed(() => (props.activeText !== '' ? props.activeText : t('input.switchOn')))
const inactiveLabel = computed(() =>
  props.inactiveText !== '' ? props.inactiveText : t('input.switchOff'),
)
const unsetLabel = computed(() => t('input.notSet'))

const isUnset = computed(() => props.threeState && current.value === null)

const readonlyText = computed(() => {
  if (current.value === null) {
    return props.threeState ? unsetLabel.value : inactiveLabel.value
  }
  return current.value ? activeLabel.value : inactiveLabel.value
})

const statusText = computed(() => readonlyText.value)

const helpText = computed(() => (isUnset.value ? t('input.notSet') : props.help))

function handleShellValue(value: unknown): void {
  current.value = normalizeBooleanValue(value)
  emit('update:modelValue', current.value)
}

function handleShellChange(value: unknown): void {
  emit('change', normalizeBooleanValue(value))
}

function handleShellValidate(shellValid: boolean): void {
  emit('validate', shellValid)
}

/** 切换单入口（内核与契约共用）：加载态 / 危险确认取消时不写值 */
async function toggle(): Promise<void> {
  if (props.loading) {
    return
  }
  const next = current.value !== true
  if (props.dangerConfirm !== '' && next === false) {
    const accepted = await confirm({ message: props.dangerConfirm, danger: true })
    if (!accepted) {
      return
    }
  }
  shellRef.value?.setValue(next)
}

function clear(): void {
  if (props.loading) {
    return
  }
  shellRef.value?.setValue(null)
}

/** 内核切换：危险确认（转为关闭）经确认后写值 */
function handleInnerUpdate(value: unknown): void {
  const next = normalizeBooleanValue(value)
  if (next === current.value) {
    return
  }
  if (props.dangerConfirm !== '' && next === false) {
    void confirm({ message: props.dangerConfirm, danger: true }).then((accepted) => {
      if (accepted) {
        shellRef.value?.setValue(false)
      }
    })
    return
  }
  shellRef.value?.setValue(next)
}

defineExpose({ toggle, clear })
</script>

<template>
  <BaseInput
    ref="shellRef"
    v-bind="$attrs"
    :class="base.nsClass('switch-input')"
    :model-value="modelValue"
    :label="label"
    :required="required"
    :help="helpText"
    :error="error"
    :disabled="disabled"
    :readonly="readonly"
    :readonly-mode="readonlyMode"
    :size="size"
    :density="density"
    :span="span"
    :trim="false"
    :field-key="fieldKey"
    :display-text="readonlyText"
    @update:model-value="handleShellValue"
    @change="handleShellChange"
    @validate="handleShellValidate"
  >
    <template #default="slot">
      <div
        :class="[base.nsClass('switch-input-control'), loading ? 'is-loading' : '']"
        data-testid="switch-input"
      >
        <VanSwitch
          :model-value="current === true"
          :loading="loading"
          :disabled="slot.disabled"
          :class="[slot.invalid ? 'is-error' : '', isUnset ? 'is-unset' : '']"
          data-testid="switch-input-switch"
          @update:model-value="handleInnerUpdate"
        />
        <span :class="base.nsClass('switch-input-text')" data-testid="switch-input-text">
          {{ statusText }}
        </span>
        <button
          v-if="allowClear && threeState && current !== null && !slot.disabled"
          type="button"
          :class="base.nsClass('switch-input-clear')"
          data-testid="switch-input-clear"
          @click="clear"
        >
          ×
        </button>
      </div>
    </template>
  </BaseInput>
</template>

<style scoped>
.bms-switch-input-control {
  display: flex;
  gap: var(--bms-space-2);
  align-items: center;
  min-height: var(--bms-size-control-height);
}

.bms-switch-input-text {
  font-size: var(--bms-font-size-base);
  color: var(--bms-color-text);
}

.bms-switch-input-control.is-loading .bms-switch-input-text {
  color: var(--bms-color-text-secondary);
}

.bms-switch-input-clear {
  padding: 0 var(--bms-space-1);
  font-size: var(--bms-font-size-base);
  color: var(--bms-color-text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
}

.bms-switch-input :deep(.is-unset) {
  opacity: 0.6;
}
</style>
