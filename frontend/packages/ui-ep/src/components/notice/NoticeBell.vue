<script setup lang="ts">
// 顶栏铃铛（07_04）：未读角标（>99 显示 99+）+ 下拉最近通知 + 查看全部；单一入口，实时增量与断线补偿由编排层负责。
import { connectionLabel } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseNotification } from '../../composables/useBaseNotification'
import NoticeMessageItem from './NoticeMessageItem.vue'
import type { NoticeItem } from './NoticeList.vue'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 未读数（角标）。 */
  unreadCount?: number
  /** 最近通知列表。 */
  items?: NoticeItem[]
  /** 下拉最近条数（缺省 5）。 */
  recentLimit?: number
  /** 角标上限（缺省 99）。 */
  badgeMax?: number
  /** 实时连接状态（可选展示）。 */
  connectionState?: 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'offline'
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  unreadCount: 0,
  items: () => [],
  recentLimit: 5,
  badgeMax: 99,
  connectionState: 'idle',
  degradeText: '通知数据未就绪（占位）',
})

const emit = defineEmits<{
  open: [item: NoticeItem]
  read: [id: string]
  'read-all': []
  'view-all': []
  retry: []
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
watch(
  () => props.items,
  (next) => base.center.setItems(next),
  { immediate: true },
)

const open = ref(false)

/** 最近通知（按创建时间降序）。 */
const recentItems = computed(() => base.center.recent(props.recentLimit))

/** 角标文案。 */
const badge = computed(() => {
  const count = props.unreadCount
  if (count <= 0) {
    return ''
  }
  return count > props.badgeMax ? `${props.badgeMax}+` : String(count)
})

/** 连接状态文案。 */
const connection = computed(() => connectionLabel(props.connectionState))
</script>

<template>
  <div class="bms-notice-bell" data-test="notice-bell" :data-ready="base.ready.value" :data-degraded="base.degraded.value">
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <button type="button" class="bms-notice-bell__trigger" aria-label="通知" @click="open = !open">
        <span class="bms-notice-bell__icon" aria-hidden="true">🔔</span>
        <span v-if="badge" class="bms-notice-bell__badge" data-test="notice-badge">{{ badge }}</span>
      </button>
      <div v-if="open" class="bms-notice-bell__dropdown" data-test="notice-dropdown">
        <div class="bms-notice-bell__head">
          <span>最近通知</span>
          <span class="bms-notice-bell__connection" data-test="connection">{{ connection }}</span>
        </div>
        <ul v-if="recentItems.length > 0" class="bms-notice-bell__recent" data-test="notice-recent">
          <li v-for="item in recentItems" :key="item.id">
            <slot name="item" :item="item">
              <NoticeMessageItem
                :message="item"
                compact
                @open="emit('open', $event)"
                @read="emit('read', $event)"
              />
            </slot>
          </li>
        </ul>
        <div v-else class="bms-display-placeholder" data-test="empty">
          <slot name="empty">暂无通知</slot>
        </div>
        <div class="bms-notice-bell__foot">
          <button type="button" data-test="read-all" @click="emit('read-all')">全部已读</button>
          <button type="button" data-test="view-all" @click="emit('view-all')">查看全部</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-notice-bell {
  position: relative;
  display: inline-block;
}
.bms-notice-bell__trigger {
  position: relative;
  padding: 4px 8px;
  font-size: 18px;
  cursor: pointer;
  background: none;
  border: none;
}
.bms-notice-bell__badge {
  position: absolute;
  top: 0;
  right: 0;
  min-width: 16px;
  padding: 0 4px;
  font-size: 11px;
  line-height: 16px;
  color: #fff;
  text-align: center;
  background: var(--bms-notice-badge-bg, var(--bms-color-danger, #f56c6c));
  border-radius: 8px;
}
.bms-notice-bell__dropdown {
  position: absolute;
  right: 0;
  z-index: 2000;
  width: 320px;
  background: var(--bms-color-bg, #fff);
  border: 1px solid var(--bms-color-border, #ebeef5);
  border-radius: 4px;
  box-shadow: 0 4px 12px rgb(0 0 0 / 12%);
}
.bms-notice-bell__head,
.bms-notice-bell__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--bms-color-text-secondary, #909399);
}
.bms-notice-bell__recent {
  max-height: 360px;
  padding: 0;
  margin: 0;
  overflow: auto;
  list-style: none;
}
.bms-notice-bell__foot button {
  color: var(--bms-color-primary, #409eff);
  cursor: pointer;
  background: none;
  border: none;
}
</style>
