<script setup lang="ts">
/**
 * 骨架屏（移动端）：与内容结构一致的占位块（首屏 / 页面级加载，加载完成即替换）。
 *
 * 契约与 `ui-ep` 同源（props / 类名钩子一致）：`variant`（list / table / form / card）、`rows`、
 * `animated`、`loading`（`false` 渲染默认插槽内容）；`list` 形态经 `van-skeleton` 映射，
 * `table / form / card` 自绘补齐（Vant 无对应件），消费令牌。
 */

import { computed, useAttrs, watch } from 'vue'

import { Skeleton as VanSkeleton } from 'vant/es/skeleton'
import 'vant/es/skeleton/style'

import { useComponentBase } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    variant?: 'list' | 'table' | 'form' | 'card'
    rows?: number
    animated?: boolean
    /** 加载态；`false` 渲染默认插槽内容 */
    loading?: boolean
  }>(),
  { variant: 'list', rows: 5, animated: true, loading: true },
)

const base = useComponentBase({ ns: 'bms', identifier: 'skeleton-block' })
const attrs = useAttrs()

const rowList = computed(() =>
  Array.from({ length: Math.max(1, props.rows) }, (_, index) => index + 1),
)

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('skeleton-block'), cls], style: sty, ...rest })
})

watch(() => props.loading, (value) => base.setProps({ loading: value }), { immediate: true })
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('skeleton-block')">
    <template v-if="loading">
      <van-skeleton
        v-if="variant === 'list'"
        :row="Math.max(1, rows)"
        :animate="animated"
        :class="[base.nsClass('skeleton'), base.nsClass('skeleton--list')]"
      >
        <template #template>
          <div v-for="row in rowList" :key="row" :class="base.nsClass('skeleton-line')" />
        </template>
      </van-skeleton>

      <div
        v-else
        :class="[
          base.nsClass('skeleton'),
          base.nsClass(`skeleton--${variant}`),
          animated && 'is-animated',
        ]"
      >
        <template v-if="variant === 'table'">
          <div :class="[base.nsClass('skeleton-row'), 'is-head']">
            <div v-for="cell in 4" :key="cell" :class="base.nsClass('skeleton-cell')" />
          </div>
          <div v-for="row in rowList" :key="row" :class="base.nsClass('skeleton-row')">
            <div v-for="cell in 4" :key="cell" :class="base.nsClass('skeleton-cell')" />
          </div>
        </template>

        <template v-else-if="variant === 'form'">
          <div v-for="row in rowList" :key="row" :class="base.nsClass('skeleton-field')">
            <div :class="base.nsClass('skeleton-label')" />
            <div :class="base.nsClass('skeleton-control')" />
          </div>
        </template>

        <template v-else>
          <div :class="base.nsClass('skeleton-cover')" />
          <div :class="[base.nsClass('skeleton-line'), 'is-title']" />
          <div :class="base.nsClass('skeleton-line')" />
          <div :class="[base.nsClass('skeleton-line'), 'is-short']" />
        </template>
      </div>
    </template>

    <slot v-else />
  </div>
</template>

<style scoped>
.bms-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
}

.bms-skeleton-line {
  height: 16px;
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg-page);
}

.bms-skeleton-line.is-title {
  width: 40%;
}

.bms-skeleton-line.is-short {
  width: 60%;
}

.bms-skeleton-row {
  display: flex;
  gap: var(--bms-space-2);
}

.bms-skeleton-row.is-head .bms-skeleton-cell {
  height: 36px;
}

.bms-skeleton-cell {
  flex: 1;
  height: 32px;
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg-page);
}

.bms-skeleton-field {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-skeleton-label {
  width: 96px;
  height: 16px;
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg-page);
}

.bms-skeleton-control {
  flex: 1;
  height: 32px;
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg-page);
}

.bms-skeleton-cover {
  height: 120px;
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-bg-page);
}

.is-animated .bms-skeleton-line,
.is-animated .bms-skeleton-cell,
.is-animated .bms-skeleton-label,
.is-animated .bms-skeleton-control,
.is-animated .bms-skeleton-cover {
  animation: bms-skeleton-shimmer 1.4s ease-in-out infinite;
}

@keyframes bms-skeleton-shimmer {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.55;
  }
}
</style>
