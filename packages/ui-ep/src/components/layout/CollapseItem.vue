<script setup lang="ts">
/**
 * 折叠面板项：名称 / 标题 / 禁用 / 懒渲染（缺省取父级 `Collapse` 的 `lazy`）。
 */

import { ElCollapseItem } from 'element-plus'
import 'element-plus/es/components/collapse/style/css'

import { computed, inject, ref, useAttrs, watch } from 'vue'

import { useComponentBase } from '@bms/vue'

import { COLLAPSE_STATE_KEY } from './collapseContext'

const props = withDefaults(
  defineProps<{
    name?: string
    title?: string
    disabled?: boolean
    /** 懒渲染（未传取父级 `Collapse` 的 `lazy`） */
    lazy?: boolean
  }>(),
  { name: undefined, title: '', disabled: false, lazy: undefined },
)

const base = useComponentBase({ ns: 'bms', identifier: 'collapse-item' })
const attrs = useAttrs()

const collapse = inject(COLLAPSE_STATE_KEY, null)

const isLazy = computed(() => props.lazy ?? collapse?.lazy.value ?? false)
const opened = computed(
  () => props.name !== undefined && (collapse?.active.value ?? []).includes(props.name),
)
const everOpened = ref(false)

watch(
  opened,
  (value) => {
    if (value) {
      everOpened.value = true
    }
  },
  { immediate: true },
)

const renderContent = computed(() => !isLazy.value || everOpened.value)

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('collapse-item'), cls], style: sty, ...rest })
})
</script>

<template>
  <el-collapse-item v-bind="elAttrs" :name="name" :title="title" :disabled="disabled">
    <div v-if="renderContent">
      <slot />
    </div>
  </el-collapse-item>
</template>
