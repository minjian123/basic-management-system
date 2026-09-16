<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
/**
 * 折叠面板组：手风琴 / 多开、图标位置、懒渲染、展开项持久化（《组件设计 · 折叠面板》）。
 *
 * 内容懒渲染由 `CollapseItem` 消费（`provide` 下发）；`persistKey` 经 `usePersistedState`
 * 持久化展开项（非受控模式下）。
 */

import { ElCollapse } from 'element-plus'
import 'element-plus/es/components/collapse/style/css'

import { computed, provide, ref, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'
import { usePersistedState } from '@bms/vue'

import { COLLAPSE_STATE_KEY } from './collapseContext'

const props = withDefaults(
  defineProps<{
    /** 展开项（v-model；accordion 时单值） */
    modelValue?: string | string[]
    accordion?: boolean
    iconPosition?: 'left' | 'right'
    /** 首次展开才渲染内容 */
    lazy?: boolean
    /** 展开项持久化键（按需；非受控模式生效） */
    persistKey?: string
  }>(),
  { modelValue: undefined, accordion: false, iconPosition: 'right', lazy: false, persistKey: '' },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | string[]]
  change: [value: string | string[]]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'collapse' })
const attrs = useAttrs()

function normalize(value: unknown): string[] {
  if (value === undefined || value === '') {
    return []
  }
  const list = Array.isArray(value) ? value : [value]
  return list
    .filter((item) => item !== undefined && item !== null)
    .map((item) => String(item))
}

const persist = props.persistKey.trim()
  ? usePersistedState<string[]>({ key: `${props.persistKey.trim()}:expanded`, defaultValue: [] })
  : null

const controlled = computed(() => props.modelValue !== undefined)
const inner = ref<string[]>(
  (persist?.get() as string[] | undefined) ?? normalize(props.modelValue),
)
const active = computed(() => (controlled.value ? normalize(props.modelValue) : inner.value))

provide(COLLAPSE_STATE_KEY, {
  active,
  lazy: computed(() => props.lazy),
})

function onUpdate(value: unknown): void {
  const next = normalize(value)
  if (!controlled.value) {
    inner.value = next
    persist?.set(next)
  }
  const payload: string | string[] = props.accordion ? (next[0] ?? '') : next
  emit('update:modelValue', payload)
  emit('change', payload)
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('collapse'), base.nsClass(`collapse--icon-${props.iconPosition}`), cls],
    style: sty,
    ...rest,
  })
})
</script>

<template>
  <el-collapse
    v-bind="elAttrs"
    :model-value="accordion ? (active[0] ?? '') : active"
    :accordion="accordion"
    @update:model-value="onUpdate"
  >
    <slot />
  </el-collapse>
</template>
