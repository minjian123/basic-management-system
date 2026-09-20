<script setup lang="ts">
// 通知列表（07_04）：占位降级 / 类型与已读筛选 / 分页 / 批量与全部已读 / 单条删除 / 三态；经通知件投影挂链。
// 对外契约保持 07_01 冻结形状，仅向后兼容新增可选 Props / 事件 / 插槽。
import { watch } from 'vue'

import { useBaseNotification } from '../../composables/useBaseNotification'
import NoticeMessageItem from './NoticeMessageItem.vue'

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
  /** 业务来源类型。 */
  bizType?: string
  /** 业务来源单据 id。 */
  bizId?: string
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
  /** 总数（分页用）。 */
  total?: number
  /** 当前页。 */
  page?: number
  /** 页长。 */
  pageSize?: number
  /** 类型筛选。 */
  typeFilter?: NoticeType | 'all'
  /** 已读筛选。 */
  readFilter?: 'all' | 'unread' | 'read'
  /** 是否可勾选（批量已读）。 */
  selectable?: boolean
  /** 已选 id 集合。 */
  selectedIds?: string[]
  /** 错误态。 */
  error?: boolean
  /** 首次加载（骨架屏）。 */
  firstLoad?: boolean
  /** 空态文案。 */
  emptyText?: string
  /** 显示头部。 */
  showHeader?: boolean
  /** 显示筛选区。 */
  showFilter?: boolean
  /** 错误文案。 */
  errorText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  items: () => [],
  loading: false,
  unreadCount: 0,
  compact: false,
  degradeText: '通知数据未就绪（占位）',
  total: 0,
  page: 1,
  pageSize: 20,
  typeFilter: 'all',
  readFilter: 'all',
  selectable: false,
  selectedIds: () => [],
  error: false,
  firstLoad: false,
  emptyText: '暂无通知',
  showHeader: true,
  showFilter: false,
  errorText: '通知加载失败',
})

const emit = defineEmits<{
  open: [item: NoticeItem]
  read: [id: string]
  'read-all': []
  remove: [id: string]
  'update:page': [page: number]
  'update:pageSize': [pageSize: number]
  'update:typeFilter': [type: NoticeType | 'all']
  'update:readFilter': [read: 'all' | 'unread' | 'read']
  'update:selectedIds': [ids: string[]]
  'read-batch': [ids: string[]]
  retry: []
  'selection-change': [ids: string[]]
}>()

const base = useBaseNotification({ ready: props.ready, unreadCount: props.unreadCount })

watch(
  () => props.ready,
  (next) => base.setReady(next),
)

watch(
  () => props.unreadCount,
  (next) => base.setUnreadCount(next),
)

/** 总页数。 */
const pageCount = (): number => {
  if (!props.total || !props.pageSize) {
    return 1
  }
  return Math.max(1, Math.ceil(props.total / props.pageSize))
}

/** 切换勾选并上抛。 */
function toggleSelect(id: string): void {
  const next = props.selectedIds.includes(id)
    ? props.selectedIds.filter((item) => item !== id)
    : [...props.selectedIds, id]
  emit('update:selectedIds', next)
  emit('selection-change', next)
}

/** 全选当前页（保留其它已选项）。 */
function toggleSelectAll(): void {
  const pageIds = props.items.map((item) => item.id)
  const allSelected = pageIds.every((id) => props.selectedIds.includes(id))
  const next = allSelected
    ? props.selectedIds.filter((id) => !pageIds.includes(id))
    : [...new Set([...props.selectedIds, ...pageIds])]
  emit('update:selectedIds', next)
  emit('selection-change', next)
}

/** 批量已读。 */
function emitBatchRead(): void {
  if (props.selectedIds.length > 0) {
    emit('read-batch', [...props.selectedIds])
  }
}

/** 翻页。 */
function goPage(offset: number): void {
  const next = Math.min(Math.max(1, props.page + offset), pageCount())
  if (next !== props.page) {
    emit('update:page', next)
  }
}
</script>

<template>
  <div
    class="bms-notice-list"
    data-test="notice-list"
    :data-ready="base.ready.value"
    :data-degraded="base.degraded.value"
    :data-compact="compact || undefined"
  >
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="header" :unread-count="unreadCount">
        <div v-if="showHeader" class="bms-notice-list__header" data-test="header">
          <span data-test="unread-count">未读 {{ unreadCount }}</span>
          <button type="button" data-test="read-all" @click="emit('read-all')">全部已读</button>
        </div>
      </slot>
      <slot name="filter">
        <div v-if="showFilter" class="bms-notice-list__filter" data-test="filter">
          <select
            class="bms-notice-list__select"
            data-test="filter-type"
            :value="typeFilter"
            @change="emit('update:typeFilter', ($event.target as HTMLSelectElement).value as NoticeType | 'all')"
          >
            <option value="all">全部类型</option>
            <option value="notice">站内信</option>
            <option value="todo">待办提醒</option>
            <option value="system">系统提示</option>
          </select>
          <select
            class="bms-notice-list__select"
            data-test="filter-read"
            :value="readFilter"
            @change="emit('update:readFilter', ($event.target as HTMLSelectElement).value as 'all' | 'unread' | 'read')"
          >
            <option value="all">全部</option>
            <option value="unread">未读</option>
            <option value="read">已读</option>
          </select>
          <button v-if="selectable" type="button" data-test="read-batch" @click="emitBatchRead">批量已读</button>
          <label v-if="selectable" class="bms-notice-list__select-all">
            <input type="checkbox" data-test="select-all" @change="toggleSelectAll" />
            全选本页
          </label>
        </div>
      </slot>
      <slot name="error">
        <div v-if="error" class="bms-notice-list__error" data-test="error">
          <span>{{ errorText }}</span>
          <button type="button" data-test="retry" @click="emit('retry')">重试</button>
        </div>
      </slot>
      <div v-if="!error && (firstLoad || loading)" class="bms-notice-list__skeleton" data-test="skeleton">
        <span v-for="index in 3" :key="index" class="bms-notice-list__skeleton-row" />
      </div>
      <ul v-else-if="items.length > 0" class="bms-notice-list__items" data-test="items">
        <li
          v-for="item in items"
          :key="item.id"
          class="bms-notice-list__item"
          :data-test="`notice-${item.id}`"
          :data-unread="!item.read || undefined"
          @click="emit('open', item)"
        >
          <input
            v-if="selectable"
            class="bms-notice-list__checkbox"
            type="checkbox"
            :data-test="`select-${item.id}`"
            :checked="selectedIds.includes(item.id)"
            @click.stop
            @change="toggleSelect(item.id)"
          />
          <slot name="item" :item="item">
            <NoticeMessageItem
              :message="item"
              :compact="compact"
              show-type
              show-remove
              @open="emit('open', $event)"
              @read="emit('read', $event)"
              @remove="emit('remove', $event)"
            >
              <template v-if="$slots['item-actions']" #actions="scope">
                <slot name="item-actions" v-bind="scope" />
              </template>
            </NoticeMessageItem>
          </slot>
        </li>
      </ul>
      <div v-else class="bms-notice-list__empty" data-test="empty">
        <slot name="empty">{{ emptyText }}</slot>
      </div>
      <div v-if="!error && total > 0" class="bms-notice-list__pagination" data-test="pagination">
        <button type="button" :disabled="page <= 1" @click="goPage(-1)">上一页</button>
        <span class="bms-notice-list__page" data-test="page">{{ page }} / {{ pageCount() }}</span>
        <button type="button" :disabled="page >= pageCount()" @click="goPage(1)">下一页</button>
      </div>
      <slot name="footer" />
    </template>
  </div>
</template>

<style scoped>
.bms-notice-list {
  display: flex;
  flex-direction: column;
}
.bms-notice-list__header,
.bms-notice-list__filter {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
}
.bms-notice-list__header {
  justify-content: space-between;
  border-bottom: 1px solid var(--bms-color-border);
}
.bms-notice-list__header button {
  color: var(--bms-color-primary);
  cursor: pointer;
  background: none;
  border: none;
}
.bms-notice-list__items {
  padding: 0;
  margin: 0;
  list-style: none;
}
.bms-notice-list__item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-left: 8px;
}
.bms-notice-list__empty,
.bms-notice-list__error {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 32px;
  color: var(--bms-color-text-secondary);
}
.bms-notice-list__skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}
.bms-notice-list__skeleton-row {
  height: 16px;
  background: var(--bms-notice-item-hover-bg);
  border-radius: 4px;
}
.bms-notice-list__pagination {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  padding: 8px 12px;
}
</style>
