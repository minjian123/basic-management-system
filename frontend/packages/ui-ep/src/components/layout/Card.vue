<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
/**
 * 卡片：标题 / 描述 / 操作 / 内容 / 底栏 / 封面，可折叠与加载态（《组件设计 · 卡片》）。
 *
 * 容器语义复用组件根与令牌；`loading` 以骨架（`03_02`）替换内容；折叠经 `v-model:collapsed`。
 */

import { ElCard } from 'element-plus'
import 'element-plus/es/components/card/style/css'

import { computed, useAttrs, useSlots } from 'vue'

import { useComponentBase } from '@bms/vue'
import SkeletonBlock from '../feedback/SkeletonBlock.vue'

const props = withDefaults(
  defineProps<{
    title?: string
    description?: string
    collapsible?: boolean
    /** 折叠态（v-model:collapsed） */
    collapsed?: boolean
    hoverable?: boolean
    /** 加载态（骨架替换内容） */
    loading?: boolean
    bordered?: boolean
  }>(),
  {
    title: '',
    description: '',
    collapsible: false,
    collapsed: false,
    hoverable: false,
    loading: false,
    bordered: true,
  },
)

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'collapse-change': [value: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'card' })
const attrs = useAttrs()
const slots = useSlots()

function toggle(): void {
  const next = !props.collapsed
  emit('update:collapsed', next)
  emit('collapse-change', next)
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('card'), props.hoverable && 'is-hoverable', cls], style: sty, ...rest })
})
</script>

<template>
  <el-card v-bind="elAttrs" :bordered="bordered" :shadow="hoverable ? 'hover' : 'never'">
    <template #header>
      <div :class="base.nsClass('card-head')">
        <div :class="base.nsClass('card-head-main')">
          <slot name="title">
            <span :class="base.nsClass('card-title')">{{ title }}</span>
          </slot>
          <span v-if="description" :class="base.nsClass('card-description')">{{ description }}</span>
        </div>
        <div :class="base.nsClass('card-head-extra')">
          <slot name="extra" />
          <span
            v-if="collapsible"
            :class="base.nsClass('card-collapse-toggle')"
            role="button"
            @click="toggle"
          >
            {{ collapsed ? '▸' : '▾' }}
          </span>
        </div>
      </div>
    </template>

    <div v-if="slots.cover" :class="base.nsClass('card-cover')">
      <slot name="cover" />
    </div>

    <div v-show="!collapsed">
      <SkeletonBlock v-if="loading" variant="card" :rows="3" />
      <slot v-else />
    </div>

    <template v-if="slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-card>
</template>

<style scoped>
.bms-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bms-space-2);
}

.bms-card-head-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.bms-card-title {
  font-weight: var(--bms-font-weight-semibold);
}

.bms-card-description {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-card-head-extra {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-1);
}

.bms-card-collapse-toggle {
  padding: 0 4px;
  border-radius: var(--bms-radius-sm);
  color: var(--bms-color-text-secondary);
  cursor: pointer;
}

.bms-card-collapse-toggle:hover {
  background: var(--bms-color-bg-page);
  color: var(--bms-color-text);
}

.bms-card-cover {
  margin-bottom: var(--bms-space-2);
}
</style>
