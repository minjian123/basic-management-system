<script setup lang="ts">
/**
 * 空状态（移动端）：场景矩阵（列表 / 搜索 / 待办 / 消息 / 自定义）+ 引导按钮（《布局设计 · 异常与空状态》）。
 *
 * 契约与 `ui-ep` 同源（props / emits / 类名钩子一致）：场景决定缺省插画 / 文案；引导按钮
 * `actionPerm` 无权限不渲染；`size='small'` 供卡片内紧凑场景；视觉经 `van-empty` 映射，
 * 插画统一 `src/assets/images/empty-*.svg`（不内联大段 SVG）。
 */

import { useI18n } from 'vue-i18n'
import { computed, useAttrs } from 'vue'

import { Button as VanButton } from 'vant/es/button'
import { Empty as VanEmpty } from 'vant/es/empty'
import 'vant/es/button/style'
import 'vant/es/empty/style'

import { useComponentBase } from '@bms/vue'
import { checkPerm } from '../../permission'

import emptyList from '../../assets/images/empty-list.svg'
import emptyMessage from '../../assets/images/empty-message.svg'
import emptySearch from '../../assets/images/empty-search.svg'
import emptyTodo from '../../assets/images/empty-todo.svg'

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
/** 插画尺寸（与令牌 `--bms-illustration-size` 同值；small 档紧凑） */
const imageSize = computed(() => (props.size === 'small' ? 56 : 96))

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
  if (props.actionPerm && !checkPerm(props.actionPerm)) {
    return false
  }
  return Boolean(actionText.value)
})

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('empty-state'), props.size === 'small' && base.nsClass('empty-state--small'), cls],
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
    <van-empty :image="illustration" :image-size="imageSize">
      <template #description>
        <p v-if="titleText" :class="base.nsClass('empty-state-title')">{{ titleText }}</p>
        <p v-if="description" :class="base.nsClass('empty-state-description')">{{ description }}</p>
      </template>
      <div v-if="actionVisible" :class="base.nsClass('empty-state-action')">
        <van-button
          size="small"
          :type="action?.type === 'primary' ? 'primary' : 'default'"
          @click="onAction"
        >
          {{ actionText }}
        </van-button>
      </div>
      <slot />
    </van-empty>
  </div>
</template>

<style scoped>
.bms-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--bms-color-text);
  text-align: center;
}

.bms-empty-state :deep(.van-empty) {
  padding: var(--bms-space-6) var(--bms-space-4);
}

.bms-empty-state :deep(.van-empty__image) {
  width: var(--bms-illustration-size);
  height: var(--bms-illustration-size);
}

.bms-empty-state--small :deep(.van-empty) {
  padding: var(--bms-space-3) var(--bms-space-2);
}

.bms-empty-state :deep(.van-empty__description) {
  margin-top: var(--bms-space-2);
}

.bms-empty-state-title {
  margin: 0;
  font-size: var(--bms-font-size-base);
  font-weight: var(--bms-font-weight-medium);
}

.bms-empty-state-description {
  margin: var(--bms-space-1) 0 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.bms-empty-state-action {
  margin-top: var(--bms-space-2);
}
</style>
