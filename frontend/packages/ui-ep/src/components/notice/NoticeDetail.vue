<script setup lang="ts">
// 通知详情（07_04）：抽屉形态；标题 / 类型 / 时间 / 内容，查看即已读（幂等），跳转业务单据。
import { ElDrawer } from 'element-plus'
import { formatDateTime, formatRelativeTime, resolveMessageSemantic } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseNotification } from '../../composables/useBaseNotification'
import type { NoticeItem } from './NoticeList.vue'

interface Props {
  /** 显隐。 */
  modelValue: boolean
  /** 消息。 */
  message?: NoticeItem | null
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 加载中。 */
  loading?: boolean
  /** 允许跳转（缺省 true）。 */
  jumpEnabled?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  message: null,
  ready: false,
  loading: false,
  jumpEnabled: true,
  degradeText: '通知数据未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  read: [id: string]
  jump: [target: { bizType: string; bizId: string }]
  close: []
}>()

const base = useBaseNotification({ ready: props.ready })

watch(
  () => props.ready,
  (next) => base.setReady(next),
)

/** 本次会话已触发已读的消息 id（幂等）。 */
const readIds = new Set<string>()

watch(
  () => [props.modelValue, props.message?.id] as const,
  ([visible, id]) => {
    if (!visible || !id || props.message?.read === true || readIds.has(id)) {
      return
    }
    readIds.add(id)
    emit('read', id)
  },
  { immediate: true },
)

/** 类型文案。 */
const typeLabel = computed(() => (props.message ? base.center.messageLabel(props.message.type) || '站内信' : ''))

/** 类型语义色。 */
const semantic = computed(() => resolveMessageSemantic(props.message?.type))

/** 是否可跳转。 */
const jumpTarget = computed(() => (props.message ? base.center.jumpTargetOf(props.message) : undefined))

/** 相对时间。 */
const relative = computed(() => (props.message?.createdAt ? formatRelativeTime(props.message.createdAt) : ''))

/** 绝对时间。 */
const absolute = computed(() => (props.message?.createdAt ? formatDateTime(props.message.createdAt) : ''))
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="通知详情"
    size="440px"
    data-test="notice-detail"
    :data-ready="base.ready.value"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <div v-else-if="loading" class="bms-notice-detail__loading">加载中…</div>
    <div v-else-if="message" class="bms-notice-detail">
      <div class="bms-notice-detail__head">
        <span class="bms-notice-detail__type" data-test="notice-detail-type" :class="`is-${semantic}`">{{ typeLabel }}</span>
        <span class="bms-notice-detail__time" data-test="notice-detail-time" :title="absolute">{{ relative }}</span>
      </div>
      <h3 class="bms-notice-detail__title" data-test="notice-detail-title">{{ message.title }}</h3>
      <p class="bms-notice-detail__content" data-test="notice-detail-content">{{ message.content }}</p>
      <slot name="default" :message="message" />
      <div v-if="jumpEnabled && jumpTarget" class="bms-notice-detail__foot">
        <button type="button" data-test="notice-jump" @click="emit('jump', jumpTarget)">查看单据</button>
      </div>
      <slot name="footer" :message="message" />
    </div>
  </el-drawer>
</template>

<style scoped>
.bms-notice-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bms-notice-detail__head {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}
.bms-notice-detail__type {
  padding: 0 6px;
  line-height: 18px;
  border-radius: 9px;
  background: color-mix(in srgb, currentcolor 12%, transparent);
}
.bms-notice-detail__type.is-info {
  color: var(--bms-color-info);
}
.bms-notice-detail__type.is-warning {
  color: var(--bms-color-warning);
}
.bms-notice-detail__type.is-primary {
  color: var(--bms-color-primary);
}
.bms-notice-detail__title {
  margin: 0;
  font-size: 16px;
}
.bms-notice-detail__content {
  color: var(--bms-color-text);
  white-space: pre-wrap;
}
.bms-notice-detail__foot {
  padding-top: 8px;
}
.bms-notice-detail__foot button {
  color: var(--bms-color-primary);
  cursor: pointer;
  background: none;
  border: none;
}
</style>
