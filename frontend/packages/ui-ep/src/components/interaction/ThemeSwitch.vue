<script setup lang="ts">
// 主题切换件：亮 / 暗 / 跟随系统（图标 / 分段 / 列表三形态）+ 可选强调色；切换即时生效、不刷新页面。
import { computed, ref, watch } from 'vue'

import type { ThemeMode } from '@bms/core'
import { useBaseTheme } from '../../composables/useBaseTheme'

interface Props {
  /** 当前主题模式（`v-model`）。 */
  modelValue?: ThemeMode
  /** 呈现形态。 */
  variant?: 'icon' | 'segment' | 'list'
  /** 是否显示强调色选择。 */
  showAccent?: boolean
  /** 用户强调色（`v-model:accent`）。 */
  accent?: string
  /** 是否允许暗色（品牌可禁用）。 */
  canUseDark?: boolean
  /** 是否禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: 'system',
  variant: 'icon',
  showAccent: false,
  accent: '',
  canUseDark: true,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: ThemeMode]
  'update:accent': [value: string]
  change: [payload: { mode: ThemeMode; resolved: 'light' | 'dark' }]
}>()

/** 强调色预设。 */
const PRESET_ACCENTS = ['#1677ff', '#00b96b', '#fa8c16', '#eb2f96', '#722ed1']

const { mode, resolved, displayMode, setMode, setAccent } = useBaseTheme({
  mode: props.modelValue,
  followSystem: true,
})

/** 图标形态下拉展开态。 */
const open = ref(false)

watch(
  () => props.modelValue,
  (value) => setMode(value),
)
watch(
  () => props.accent,
  (value) => setAccent(value === '' ? undefined : value),
)

/** 可选模式（禁用暗色时收窄，`system` 归一亮色展示）。 */
const options = computed(() =>
  props.canUseDark
    ? [
        { value: 'light' as ThemeMode, label: '亮色' },
        { value: 'dark' as ThemeMode, label: '暗色' },
        { value: 'system' as ThemeMode, label: '跟随系统' },
      ]
    : [
        { value: 'light' as ThemeMode, label: '亮色' },
        { value: 'system' as ThemeMode, label: '跟随系统' },
      ],
)
/** 图标形态展示符号。 */
const iconText = computed(() => (displayMode.value === 'dark' ? '🌙' : '☀'))

/**
 * 选择模式（即时生效并上抛）。
 *
 * @param value 主题模式。
 */
const choose = (value: ThemeMode): void => {
  if (props.disabled) {
    return
  }
  open.value = false
  setMode(value)
  emit('update:modelValue', value)
  emit('change', { mode: value, resolved: resolved.value })
}

/**
 * 选择强调色。
 *
 * @param color 颜色值。
 */
const chooseAccent = (color: string): void => {
  if (props.disabled) {
    return
  }
  setAccent(color)
  emit('update:accent', color)
}

/** 图标形态点击：亮暗互切。 */
const toggleMode = (): void => {
  if (props.disabled) {
    return
  }
  open.value = false
  const next: ThemeMode = displayMode.value === 'dark' ? 'light' : 'dark'
  choose(next)
}
</script>

<template>
  <div
    class="bms-theme-switch"
    :data-variant="variant"
    :data-resolved="resolved"
    data-test="theme-switch"
  >
    <template v-if="variant === 'icon'">
      <button
        type="button"
        class="bms-theme-switch__icon"
        :disabled="disabled"
        data-test="theme-switch-icon"
        @click="toggleMode"
      >
        {{ iconText }}
      </button>
      <button
        type="button"
        class="bms-theme-switch__link"
        :disabled="disabled"
        data-test="theme-switch-menu-toggle"
        @click="open = !open"
      >
        主题
      </button>
      <span v-if="open" class="bms-theme-switch__menu" data-test="theme-switch-menu">
        <button
          v-for="option in options"
          :key="option.value"
          type="button"
          class="bms-theme-switch__menu-item"
          :data-active="mode === option.value ? 'true' : 'false'"
          :data-test="`theme-switch-option-${option.value}`"
          @click="choose(option.value)"
        >
          {{ option.label }}
        </button>
      </span>
    </template>

    <template v-else>
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        class="bms-theme-switch__option"
        :data-active="mode === option.value ? 'true' : 'false'"
        :data-test="`theme-switch-option-${option.value}`"
        :disabled="disabled"
        @click="choose(option.value)"
      >
        {{ variant === 'segment' ? option.label : `${option.label}${mode === option.value ? ' ✓' : ''}` }}
      </button>
    </template>

    <span v-if="showAccent" class="bms-theme-switch__accents" data-test="theme-switch-accents">
      <button
        v-for="color in PRESET_ACCENTS"
        :key="color"
        type="button"
        class="bms-theme-switch__accent"
        :style="{ background: color }"
        :data-active="accent === color ? 'true' : 'false'"
        :data-test="`theme-switch-accent-${color.replace('#', '')}`"
        :disabled="disabled"
        @click="chooseAccent(color)"
      />
    </span>
  </div>
</template>

<style scoped>
.bms-theme-switch {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  position: relative;
}

.bms-theme-switch__icon,
.bms-theme-switch__option {
  padding: 4px 10px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 4px);
  background: var(--bms-color-bg, #ffffff);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-theme-switch__option[data-active='true'] {
  border-color: var(--bms-color-primary, #1677ff);
  color: var(--bms-color-primary, #1677ff);
}

.bms-theme-switch__icon:disabled,
.bms-theme-switch__option:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-theme-switch__link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--bms-color-primary, #1677ff);
  font: inherit;
  cursor: pointer;
}

.bms-theme-switch__menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  display: flex;
  flex-direction: column;
  min-width: 120px;
  padding: 4px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 4px);
  background: var(--bms-color-bg, #ffffff);
  box-shadow: var(--bms-shadow-sm, 0 2px 8px rgba(0, 0, 0, 0.12));
  z-index: 20;
}

.bms-theme-switch__menu-item {
  padding: 4px 8px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.bms-theme-switch__menu-item[data-active='true'] {
  color: var(--bms-color-primary, #1677ff);
}

.bms-theme-switch__accents {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.bms-theme-switch__accent {
  width: 16px;
  height: 16px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: 50%;
  cursor: pointer;
}

.bms-theme-switch__accent[data-active='true'] {
  outline: 2px solid var(--bms-color-primary, #1677ff);
  outline-offset: 1px;
}
</style>
