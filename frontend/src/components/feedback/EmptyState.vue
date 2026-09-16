<script setup lang="ts">
/**
 * 空状态：场景矩阵（列表 / 搜索 / 待办 / 消息 / 自定义）+ 引导按钮（《布局设计 · 异常与空状态》）。
 *
 * 契约见《组件设计 · 异常与空状态》§4：场景决定缺省插画 / 文案；引导按钮 `actionPerm`
 * 无权限不渲染；`size='small'` 供表格内 / 卡片内；优先文案引导而非纯插画；插画统一
 * `src/assets/images/empty-*.svg`（不内联大段 SVG）。
 */

import { useI18n } from 'vue-i18n'
import { computed, useAttrs } from 'vue'

import emptyList from '@/assets/images/empty-list.svg'
import emptyMessage from '@/assets/images/empty-message.svg'
import emptySearch from '@/assets/images/empty-search.svg'
import emptyTodo from '@/assets/images/empty-todo.svg'
import { useComponentBase } from '@/base/useComponentBase'
import { hasPerm } from '@/utils/perm'

import type { FeedbackAction } from './types'

type EmptyStateType = 'list' | 'search' | 'todo' | 'message' | 'custom'

const props = withDefaults(
  defineProps<{
    type?: EmptyStateType
    title?: string | null
    description?: string | null
    /** 自定义插画 URL（缺省按 type 映射内置 `empty-*.svg`） */
    image?: string | null
    /** 引导按钮（`text` 缺省按场景：list → 去创建、search → 清除筛选） */
    action?: FeedbackAction | null
    /** 引导按钮权限码（无权限不渲染） */
    actionPerm?: string | null
    size?: 'default' | 'small'
  }>(),
  {
    type: 'list',
    title: null,
    description: null,
    image: null,
    action: null,
    actionPerm: null,
    size: 'default',
  },
)

const emit = defineEmits<{ action: [] }>()

const base = useComponentBase({ ns: 'bms', identifier: 'empty-state' })
const { t } = useI18n()
const attrs = useAttrs()

const ILLUSTRATIONS: Record<EmptyStateType, string> = {
  list: emptyList,
  search: emptySearch,
  todo: emptyTodo,
  message: emptyMessage,
  custom: emptyList,
}

const TITLE_KEYS: Record<EmptyStateType, string> = {
  list: 'feedback.emptyList',
  search: 'feedback.emptySearch',
  todo: 'feedback.emptyTodo',
  message: 'feedback.emptyMessage',
  custom: '',
}

const DEFAULT_ACTION_TEXT: Record<EmptyStateType, string> = {
  list: 'feedback.goCreate',
  search: 'feedback.clearFilters',
  todo: '',
  message: '',
  custom: '',
}

const illustration = computed(() => props.image ?? ILLUSTRATIONS[props.type])
const titleText = computed(() => {
  if (props.title !== null) {
    return props.title
  }
  const key = TITLE_KEYS[props.type]
  return key ? t(key) : ''
})

const actionText = computed(() => {
  if (props.action?.text) {
    return props.action.text
  }
  const key = DEFAULT_ACTION_TEXT[props.type]
  return key ? t(key) : ''
})

const actionVisible = computed(() => {
  if (!props.action) {
    return false
  }
  if (props.actionPerm && !hasPerm(props.actionPerm)) {
    return false
  }
  return Boolean(actionText.value)
})

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass(), props.size === 'small' && base.nsClass('empty-state--small'), cls],
    style: sty,
    ...rest,
  })
})

function onAction(): void {
  emit('action')
  props.action?.handler?.()
}
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('empty-state')">
    <img :src="illustration" :class="base.nsClass('empty-state-illustration')" alt="" />
    <p v-if="titleText" :class="base.nsClass('empty-state-title')">{{ titleText }}</p>
    <p v-if="description" :class="base.nsClass('empty-state-description')">{{ description }}</p>
    <div v-if="actionVisible" :class="base.nsClass('empty-state-action')">
      <el-button :type="action?.type === 'primary' ? 'primary' : 'default'" @click="onAction">
        {{ actionText }}
      </el-button>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.bms-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-8) var(--bms-space-4);
  color: var(--bms-color-text);
  text-align: center;
}

.bms-empty-state-illustration {
  width: 96px;
  height: 96px;
  color: var(--bms-color-text-secondary);
}

.bms-empty-state-title {
  margin: 0;
  font-size: var(--bms-font-size-base);
  font-weight: var(--bms-font-weight-medium);
}

.bms-empty-state-description {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.bms-empty-state-action {
  margin-top: var(--bms-space-1);
}

/* small：表格内 / 卡片内紧凑尺寸 */
.bms-empty-state--small {
  gap: var(--bms-space-1);
  padding: var(--bms-space-4) var(--bms-space-2);
}

.bms-empty-state--small .bms-empty-state-illustration {
  width: 56px;
  height: 56px;
}
</style>
