<script setup lang="ts">
// 审计差异查看（占位版，07_01）：契约先行冻结；数据通路未就绪时不请求、降级提示。
import { watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'

/** 链校验状态。 */
export type AuditChainStatus = 'unknown' | 'valid' | 'invalid'

/** 变更记录行。 */
export interface AuditRecord {
  /** 主键。 */
  id: string
  /** 表名。 */
  tableName: string
  /** 记录 ID。 */
  recordId: string
  /** 变更字段数。 */
  fields?: number
  /** 操作人。 */
  operator?: string
  /** 变更时间。 */
  createdAt?: string
  /** 链状态。 */
  chainStatus?: AuditChainStatus
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 变更记录。 */
  records?: AuditRecord[]
  /** 加载中。 */
  loading?: boolean
  /** 当前页。 */
  page?: number
  /** 总条数。 */
  total?: number
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  records: () => [],
  loading: false,
  page: 1,
  total: 0,
  degradeText: '审计数据未就绪（占位）',
})

const emit = defineEmits<{
  query: []
  select: [record: AuditRecord]
  verify: [id?: string]
  'update:page': [page: number]
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)
</script>

<template>
  <div class="bms-audit-diff" :data-ready="placeholder.ready.value" :data-degraded="placeholder.degraded.value">
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-audit-diff__toolbar" data-test="toolbar">
        <button type="button" data-test="query" @click="emit('query')">查询</button>
        <button type="button" data-test="verify" @click="emit('verify')">链校验</button>
      </div>
      <ul v-if="records.length > 0" class="bms-audit-diff__records" data-test="records">
        <li
          v-for="record in records"
          :key="record.id"
          class="bms-audit-diff__record"
          :data-test="`record-${record.id}`"
          :data-chain="record.chainStatus ?? 'unknown'"
          @click="emit('select', record)"
        >
          <span data-test="table-name">{{ record.tableName }}</span>
          <span data-test="record-id">{{ record.recordId }}</span>
          <span data-test="field-count">{{ record.fields ?? 0 }} 项</span>
          <span data-test="operator">{{ record.operator }}</span>
          <span data-test="created-at">{{ record.createdAt }}</span>
        </li>
      </ul>
      <div v-else class="bms-audit-diff__empty" data-test="empty">
        <slot name="empty">暂无变更记录</slot>
      </div>
      <div class="bms-audit-diff__footer" data-test="footer">
        <span data-test="total">共 {{ total }} 条</span>
        <button type="button" data-test="prev" :disabled="page <= 1" @click="emit('update:page', page - 1)">
          上一页
        </button>
        <span data-test="page">{{ page }}</span>
        <button type="button" data-test="next" @click="emit('update:page', page + 1)">下一页</button>
      </div>
    </template>
  </div>
</template>
