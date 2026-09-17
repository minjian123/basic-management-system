<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
/**
 * 内容页签：页面内容区的页签切换（区别于页面级多标签 `TabsNav`）（《组件设计 · 内容页签》）。
 *
 * 配套子项 `TabPane`（薄包装）；`lazy` 经 `provide` 下发给子项默认值（切换才挂载）。
 */

import { computed, provide, useAttrs } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

import { TABS_LAZY_KEY } from './tabsContext'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    type?: 'line' | 'card' | 'border-card'
    closable?: boolean
    addable?: boolean
    /** 懒渲染（切换才挂载；子项可覆盖） */
    lazy?: boolean
    stretch?: boolean
  }>(),
  { modelValue: '', type: 'line', closable: false, addable: false, lazy: true, stretch: false },
)

const emit = defineEmits<{
  'update:modelValue': [key: string]
  'tab-change': [key: string]
  'tab-remove': [key: string]
  'tab-add': []
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'tabs' })
const attrs = useAttrs()

provide(
  TABS_LAZY_KEY,
  computed(() => props.lazy),
)

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('tabs'), cls], style: sty, ...rest })
})
</script>

<template>
  <el-tabs
    v-bind="elAttrs"
    :model-value="modelValue"
    :type="type"
    :closable="closable"
    :addable="addable"
    :stretch="stretch"
    @update:model-value="emit('update:modelValue', $event)"
    @tab-change="emit('tab-change', $event)"
    @tab-remove="emit('tab-remove', $event)"
    @tab-add="emit('tab-add')"
  >
    <slot />
  </el-tabs>
</template>
