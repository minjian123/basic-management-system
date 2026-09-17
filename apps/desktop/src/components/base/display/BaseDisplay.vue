<script setup lang="ts">
/**
 * 展示域组件包装（`BaseDisplay`）：展示域基类的组件轨（**框架无关**）。
 *
 * 契约见《组件设计 · 展示域基类》：只读值渲染（`value` + `formatter`）、统一空值占位、
 * 超长省略与 tooltip、可复制；不接收 `modelValue`、不参与校验。
 * 兜底渲染 `<span>` + `title` + 复制按钮；具体展示（标签 / 头像 / 链接）由子类插槽接入。
 */

import { computed, onMounted, onUnmounted, useAttrs } from 'vue'

import { normalizeClassList, type ComponentDensity, type ComponentSize } from '@/base/BaseComponent'
import { useComponentBase } from '@/base/useComponentBase'

import { useDisplayBase } from './useDisplayBase'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    ns?: string
    identifier?: string
    size?: ComponentSize
    density?: ComponentDensity
    loading?: boolean
    disabled?: boolean
    visible?: boolean
    dataTest?: string
    value?: unknown
    formatter?: string | ((value: unknown) => string)
    emptyText?: string
    copyable?: boolean
    ellipsis?: boolean | number
    tooltip?: boolean | 'overflow'
    masked?: boolean
    clickable?: boolean
  }>(),
  {
    ns: 'bms',
    identifier: '',
    size: 'default',
    density: undefined,
    loading: false,
    disabled: false,
    visible: true,
    dataTest: '',
    value: undefined,
    formatter: undefined,
    emptyText: '',
    copyable: false,
    ellipsis: false,
    tooltip: 'overflow',
    masked: false,
    clickable: false,
  },
)

const emit = defineEmits<{
  /** 复制成功 */
  copy: [value: unknown]
  /** 点击值（可点击时） */
  'click-value': [value: unknown]
}>()

const attrs = useAttrs()
const base = useComponentBase(props)

const displayBase = useDisplayBase({
  value: () => props.value,
  formatter: computed(() => props.formatter),
  emptyText: () => props.emptyText,
  density: () => base.density,
  copyable: () => props.copyable,
  ellipsis: () => props.ellipsis,
  tooltip: () => props.tooltip,
  masked: () => props.masked,
  clickable: () => props.clickable,
  onClickValue: (value) => emit('click-value', value),
  onCopy: (value) => emit('copy', value),
})

const rootAttrs = computed(() => {
  const classes = [...normalizeClassList(base.nsClass('display')), ...normalizeClassList(attrs.class)]
  const external: Record<string, unknown> = {}
  if (attrs.style !== undefined) {
    external.style = attrs.style
  }
  const merged = base.rootAttrs(external)
  if (classes.length > 0) {
    merged.class = classes
  }
  return merged
})

const onClick = (): void => {
  displayBase.onClick()
}

const onCopy = async (): Promise<void> => {
  await displayBase.copy()
}

onMounted(() => {
  base.notifyLifecycle('mounted')
})

onUnmounted(() => {
  base.notifyLifecycle('unmounted')
  base.dispose()
})

defineExpose({ base, mechanisms: base.mechanisms, displayBase })
</script>

<template>
  <span v-if="base.visible" v-bind="rootAttrs" :title="displayBase.tooltipText || undefined" @click="onClick">
    <slot v-if="displayBase.isEmpty" name="empty" :value="props.value">{{ displayBase.displayText }}</slot>
    <slot v-else :value="props.value" :text="displayBase.displayText">{{ displayBase.displayText }}</slot>
    <button v-if="displayBase.canCopy" type="button" class="bms-display__copy" aria-label="copy" @click.stop="onCopy">
      ⧉
    </button>
  </span>
</template>
