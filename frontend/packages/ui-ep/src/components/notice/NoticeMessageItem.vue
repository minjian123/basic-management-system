<script setup lang="ts">
// 消息项（07_04）：类型语义色 / 标题摘要 / 相对时间 / 未读高亮 / 跳转与删除；列表、铃铛下拉、工作台通知卡三处复用。
import { formatDateTime, formatRelativeTime, resolveMessageSemantic } from '@bms/core'
import { computed } from 'vue'

import { useBaseNotification } from '../../composables/useBaseNotification'
import type { NoticeItem } from './NoticeList.vue'

interface Props {
  /** 消息。 */
  message: NoticeItem
  /** 紧凑形态（铃铛下拉用）。 */
  compact?: boolean
  /** 显示类型标签。 */
  showType?: boolean
  /** 显示删除入口。 */
  showRemove?: boolean
  /** 未读高亮（缺省 true）。 */
  highlightUnread?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  compact: false,
  showType: true,
  showRemove: false,
  highlightUnread: true,
})

const emit = defineEmits<{
  open: [message: NoticeItem]
  read: [id: string]
  remove: [id: string]
}>()

const base = useBaseNotification({ ready: true })

/** 是否未读。 */
const unread = computed(() => props.message.read !== true)

/** 类型文案。 */
const typeLabel = computed(() => base.center.messageLabel(props.message.type) || '站内信')

/** 类型语义色。 */
const semantic = computed(() => resolveMessageSemantic(props.message.type))

/** 是否可跳转业务单据。 */
const jumpable = computed(() => base.center.jumpTargetOf(props.message) !== undefined)

/** 相对时间。 */
const relative = computed(() => (props.message.createdAt ? formatRelativeTime(props.message.createdAt) : ''))

/** 绝对时间（悬浮提示）。 */
const absolute = computed(() => (props.message.createdAt ? formatDateTime(props.message.createdAt) : ''))
</script>

<template>
  <div
    class="bms-notice-item"
    :data-test="`notice-item-${message.id}`"
    :data-unread="(highlightUnread && unread) || undefined"
    :data-compact="compact || undefined"
    :class="`is-${semantic}`"
    @click.stop="emit('open', message)"
  >
    <slot name="icon" :message="message" :semantic="semantic">
      <span class="bms-notice-item__dot" :class="`is-${semantic}`" aria-hidden="true" />
    </slot>
    <div class="bms-notice-item__body">
      <div class="bms-notice-item__title-row">
        <span v-if="showType" class="bms-notice-item__type" data-test="notice-type" :class="`is-${semantic}`">
          {{ typeLabel }}
        </span>
        <span class="bms-notice-item__title" data-test="notice-title">{{ message.title }}</span>
        <span v-if="highlightUnread && unread" class="bms-notice-item__unread" data-test="notice-unread" aria-label="未读" />
      </div>
      <div v-if="!compact && message.content" class="bms-notice-item__summary" data-test="notice-summary">
        {{ message.content }}
      </div>
      <div class="bms-notice-item__meta">
        <span v-if="relative" class="bms-notice-item__time" data-test="notice-time" :title="absolute">{{ relative }}</span>
        <span v-if="jumpable" class="bms-notice-item__jump" data-test="notice-jumpable">可跳转</span>
        <slot name="meta" :message="message" />
      </div>
    </div>
    <div class="bms-notice-item__actions">
      <slot name="actions" :message="message">
        <button v-if="unread" type="button" data-test="mark-read" @click.stop="emit('read', message.id)">标记已读</button>
        <button v-if="showRemove" type="button" data-test="remove" @click.stop="emit('remove', message.id)">删除</button>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.bms-notice-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--bms-color-border);
}
.bms-notice-item:hover {
  background: var(--bms-notice-item-hover-bg);
}
.bms-notice-item[data-unread] {
  background: var(--bms-notice-unread-bg);
}
.bms-notice-item__dot {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--bms-color-info);
}
.bms-notice-item__dot.is-info {
  background: var(--bms-color-info);
}
.bms-notice-item__dot.is-warning {
  background: var(--bms-color-warning);
}
.bms-notice-item__dot.is-primary {
  background: var(--bms-color-primary);
}
.bms-notice-item__body {
  flex: 1 1 auto;
  min-width: 0;
}
.bms-notice-item__title-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.bms-notice-item__type {
  flex: 0 0 auto;
  padding: 0 6px;
  font-size: 12px;
  line-height: 18px;
  border-radius: 9px;
  color: var(--bms-color-info);
  background: color-mix(in srgb, currentcolor 12%, transparent);
}
.bms-notice-item__type.is-info {
  color: var(--bms-color-info);
}
.bms-notice-item__type.is-warning {
  color: var(--bms-color-warning);
}
.bms-notice-item__type.is-primary {
  color: var(--bms-color-primary);
}
.bms-notice-item__title {
  overflow: hidden;
  color: var(--bms-color-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bms-notice-item[data-unread] .bms-notice-item__title {
  font-weight: 600;
}
.bms-notice-item__unread {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bms-color-danger);
}
.bms-notice-item__summary {
  overflow: hidden;
  margin-top: 2px;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bms-notice-item__meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}
.bms-notice-item__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 4px;
}
.bms-notice-item__actions button {
  padding: 0 4px;
  font-size: 12px;
  color: var(--bms-color-primary);
  cursor: pointer;
  background: none;
  border: none;
}
</style>
