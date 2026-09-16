<script setup lang="ts">
/**
 * 分区容器（《组件设计 · 分区容器》）：轻量分区（标题 / 描述 / 工具区 / 内容 / 折叠）。
 *
 * - 轻量：无边框 / 阴影（与布局类「卡片」区分）；标题行 + 分隔线 + 内容 + 可选页脚；
 * - 折叠：复用容器片段 `useContainer` 的状态机（不传 `collapsed` 为非受控、传为受控），
 *   折叠经 `v-if` 按需渲染（标题保留）；折叠开关为内置 CSS 三角（无组件库依赖）；
 * - 令牌：内边距档位消费 `--bms-space-*`，分隔线消费 `--bms-color-border`。
 */

import { computed, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'
import { useContainer } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    /** 分区标题 */
    title?: string
    /** 描述（标题下小字） */
    description?: string
    /** 可折叠（标题行显示折叠开关） */
    collapsible?: boolean
    /** 折叠态（v-model:collapsed；不传为非受控、传为受控） */
    collapsed?: boolean
    /** 标题下分隔线 */
    divider?: boolean
    /** 内边距档位（`--bms-space-*`：0 / 2 / 4 / 6） */
    padding?: 'none' | 'small' | 'default' | 'large'
  }>(),
  {
    title: '',
    description: '',
    collapsible: false,
    collapsed: undefined,
    divider: true,
    padding: 'default',
  },
)

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'collapse-change': [value: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'section-container' })
const attrs = useAttrs()

/** 受控判定在挂载时静态确定（与容器片段一致） */
const controlled = props.collapsed !== undefined

/** 档位映射（节点 `small \| large` ↔ 容器片段 `compact \| loose`；仅区域属性语义） */
const fragmentPadding = computed<'none' | 'compact' | 'default' | 'loose'>(() =>
  props.padding === 'small' ? 'compact' : props.padding === 'large' ? 'loose' : props.padding,
)

const container = useContainer({
  title: () => props.title,
  collapsible: () => props.collapsible,
  padding: () => fragmentPadding.value,
  ...(controlled ? { collapsed: () => props.collapsed as boolean } : {}),
  onCollapseChange: (next) => {
    emit('update:collapsed', next)
    emit('collapse-change', next)
  },
})

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    ...container.containerAttrs,
    class: [
      base.nsClass('section-container'),
      base.nsClass(`section-container--padding-${props.padding}`),
      container.isCollapsed && 'is-collapsed',
      cls,
    ],
    style: sty,
    ...rest,
  })
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('section-container')">
    <div
      v-if="$slots.title || title || description || collapsible || $slots.extra"
      :class="[
        base.nsClass('section-container-header'),
        divider && base.nsClass('section-container-header--divider'),
      ]"
    >
      <div :class="base.nsClass('section-container-head-main')">
        <div :class="base.nsClass('section-container-title')">
          <slot name="title">{{ title }}</slot>
        </div>
        <p v-if="description" :class="base.nsClass('section-container-description')">{{ description }}</p>
      </div>
      <div :class="base.nsClass('section-container-extra')">
        <slot name="extra" />
        <button
          v-if="collapsible"
          type="button"
          :class="base.nsClass('section-container-toggle')"
          :aria-expanded="!container.isCollapsed"
          data-testid="section-toggle"
          @click="container.toggle()"
        >
          <span :class="base.nsClass('section-container-arrow')" aria-hidden="true" />
        </button>
      </div>
    </div>

    <div
      v-if="!container.isCollapsed"
      :class="base.nsClass('section-container-content')"
      data-testid="section-content"
    >
      <slot />
    </div>

    <div
      v-if="$slots.footer && !container.isCollapsed"
      :class="base.nsClass('section-container-footer')"
    >
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.bms-section-container {
  display: flex;
  flex-direction: column;
}

.bms-section-container-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--bms-space-3);
  padding: var(--bms-space-1) 0 var(--bms-space-2);
}

.bms-section-container-header--divider {
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-section-container-head-main {
  min-width: 0;
}

.bms-section-container-title {
  font-size: var(--bms-font-size-base);
  font-weight: var(--bms-font-weight-medium);
  color: var(--bms-color-text);
}

.bms-section-container-description {
  margin: var(--bms-space-1) 0 0;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.bms-section-container-extra {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-section-container-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--bms-size-icon-large);
  height: var(--bms-size-icon-large);
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
}

.bms-section-container-arrow {
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 6px solid var(--bms-color-text-secondary);
  transform: rotate(90deg);
  transition: transform 0.15s ease;
}

.is-collapsed .bms-section-container-arrow {
  transform: rotate(0deg);
}

.bms-section-container-content {
  padding-top: var(--bms-space-3);
}

.bms-section-container-footer {
  margin-top: var(--bms-space-3);
}

.bms-section-container--padding-none .bms-section-container-content,
.bms-section-container--padding-none .bms-section-container-footer {
  padding-top: 0;
  margin-top: 0;
}

.bms-section-container--padding-small .bms-section-container-content {
  padding-top: var(--bms-space-2);
}

.bms-section-container--padding-default .bms-section-container-content {
  padding-top: var(--bms-space-3);
}

.bms-section-container--padding-large .bms-section-container-content {
  padding-top: var(--bms-space-6);
}
</style>
