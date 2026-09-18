<script setup lang="ts">
// 通知列表（占位版，07_01）：契约先行冻结；数据通路未就绪时不请求、降级提示。
import { watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'

/** 消息类型。 */
export type NoticeType = 'notice' | 'todo' | 'system'

/** 消息项。 */
export interface NoticeItem {
  /** 主键。 */
  id: string
  /** 标题。 */
  title: string
  /** 内容摘要。 */
  content?: string
  /** 类型。 */
  type?: NoticeType
  /** 是否已读。 */
  read?: boolean
  /** 创建时间。 */
  createdAt?: string
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 消息列表。 */
  items?: NoticeItem[]
  /** 加载中。 */
  loading?: boolean
  /** 未读数（角标）。 */
  unreadCount?: number
  /** 紧凑形态（铃铛下拉）。 */
  compact?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  items: () => [],
  loading: false,
  unreadCount: 0,
  compact: false,
  degradeText: '通知数据未就绪（占位）',
})

const emit = defineEmits<{
  open: [item: NoticeItem]
  read: [id: string]
  'read-all': []
  remove: [id: string]
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)
</script>

<template>
  <div
    class="bms-notice-list"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-compact="compact || undefined"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-notice-list__header" data-test="header">
        <span data-test="unread-count">未读 {{ unreadCount }}</span>
        <button type="button" data-test="read-all" @click="emit('read-all')">全部已读</button>
      </div>
      <ul v-if="items.length > 0" class="bms-notice-list__items" data-test="items">
        <li
          v-for="item in items"
          :key="item.id"
          class="bms-notice-list__item"
          :data-test="`notice-${item.id}`"
          :data-unread="!item.read || undefined"
          @click="emit('open', item)"
        >
          <slot name="item" :item="item">
            <span class="bms-notice-list__type">{{ item.type ?? 'notice' }}</span>
            <span class="bms-notice-list__title">{{ item.title }}</span>
            <span class="bms-notice-list__time">{{ item.createdAt }}</span>
            <button
              v-if="!item.read"
              type="button"
              data-test="mark-read"
              @click.stop="emit('read', item.id)"
            >
              标记已读
            </button>
            <button type="button" data-test="remove" @click.stop="emit('remove', item.id)">删除</button>
          </slot>
        </li>
      </ul>
      <div v-else class="bms-notice-list__empty" data-test="empty">
        <slot name="empty">暂无通知</slot>
      </div>
    </template>
  </div>
</template>
