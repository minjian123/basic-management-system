<script setup lang="ts">
/**
 * 栅格行：24 栅格布局（《组件设计 · 栅格》）。
 *
 * 组合布局片段 `useLayout`（断点 / 令牌）；`gutter` 建议取令牌刻度（4 / 8 / 12 / 16 / 24），
 * 非刻度值开发态告警一次（不阻断）。
 */

import { computed, useAttrs, watch } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

const props = withDefaults(
  defineProps<{
    /** 列间距（水平 / 垂直；令牌刻度 4 / 8 / 12 / 16 / 24） */
    gutter?: number | [number, number]
    justify?: 'start' | 'center' | 'end' | 'space-between' | 'space-around'
    align?: 'top' | 'middle' | 'bottom'
    wrap?: boolean
  }>(),
  { gutter: 0, justify: 'start', align: 'top', wrap: true },
)

const base = useComponentBase({ ns: 'bms', identifier: 'grid-row' })
const attrs = useAttrs()

const SPACE_SCALE = [0, 4, 8, 12, 16, 24, 32]
const warned = new Set<number>()

function checkGutter(value: number): void {
  if (import.meta.env.DEV && !warned.has(value) && !SPACE_SCALE.includes(value)) {
    warned.add(value)
    console.warn(`[GridRow] gutter 建议取令牌刻度（${SPACE_SCALE.join(' / ')}）：${value}`)
  }
}

watch(
  () => props.gutter,
  (value) => {
    if (typeof value === 'number') {
      checkGutter(value)
    } else if (Array.isArray(value)) {
      value.forEach(checkGutter)
    }
  },
  { immediate: true },
)

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('grid-row'), cls], style: sty, ...rest })
})
</script>

<template>
  <el-row v-bind="elAttrs" :gutter="gutter" :justify="justify" :align="align" :wrap="wrap">
    <slot />
  </el-row>
</template>
