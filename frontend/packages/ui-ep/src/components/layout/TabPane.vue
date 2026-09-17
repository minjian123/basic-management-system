<script setup lang="ts">
/**
 * 内容页签子项（薄包装）：`label` / `name` / `disabled` / `lazy`（缺省取 `Tabs` 的 `lazy`）。
 */

import { ElTabPane } from 'element-plus'
import 'element-plus/es/components/tabs/style/css'

import { computed, inject, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'

import { TABS_LAZY_KEY } from './tabsContext'

const props = withDefaults(
  defineProps<{
    name?: string
    label?: string
    disabled?: boolean
    /** 懒渲染（未传取父级 `Tabs` 的 `lazy`，其缺省 true） */
    lazy?: boolean
  }>(),
  { name: undefined, label: '', disabled: false, lazy: undefined },
)

const base = useComponentBase({ ns: 'bms', identifier: 'tab-pane' })
const attrs = useAttrs()

const parentLazy = inject(TABS_LAZY_KEY, null)
const lazyValue = computed(() => props.lazy ?? parentLazy?.value ?? true)

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('tab-pane'), cls], style: sty, ...rest })
})
</script>

<template>
  <el-tab-pane
    v-bind="elAttrs"
    :name="name"
    :label="label"
    :disabled="disabled"
    :lazy="lazyValue"
  >
    <slot />
  </el-tab-pane>
</template>
