<script setup lang="ts">
// 审计差异查看（07_03）：变更记录列表 + 字段级旧值→新值类型感知渲染 + 脱敏展示 + 链字段与校验结果。
import { computed, watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'
import { diffKind, formatDiffValue, type AuditValueType } from '../../utils/auditDiff'

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

/** 字段级差异项。 */
export interface AuditFieldDiff {
  /** 字段名。 */
  field: string
  /** 字段标签（缺省用字段名）。 */
  label?: string
  /** 旧值（JSON 序列化，后端已脱敏）。 */
  oldValue?: unknown
  /** 新值（JSON 序列化，后端已脱敏）。 */
  newValue?: unknown
  /** 渲染类型（缺省按值推断）。 */
  valueType?: AuditValueType
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
  /** 选中记录的字段级差异。 */
  diff?: AuditFieldDiff[]
  /** 前序哈希（链字段）。 */
  prevHash?: string
  /** 记录哈希（链字段）。 */
  recordHash?: string
  /** 链校验结果。 */
  chainVerified?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  records: () => [],
  loading: false,
  page: 1,
  total: 0,
  diff: () => [],
  prevHash: '',
  recordHash: '',
  chainVerified: undefined,
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

const showChain = computed(
  () => props.prevHash !== '' || props.recordHash !== '' || props.chainVerified !== undefined,
)

const chainText = computed(() => {
  if (props.chainVerified === true) {
    return '校验通过'
  }
  if (props.chainVerified === false) {
    return '校验异常'
  }
  return '未校验'
})

function shortHash(hash: string): string {
  return hash === '' ? '' : `${hash.slice(0, 8)}…`
}
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

      <div v-if="diff.length > 0" class="bms-audit-diff__diff" data-test="diff-panel">
        <div
          v-for="item in diff"
          :key="item.field"
          class="bms-audit-diff__field"
          :data-test="`diff-${item.field}`"
          :data-change="diffKind(item.oldValue, item.newValue)"
        >
          <span class="bms-audit-diff__label" data-test="diff-field">{{ item.label ?? item.field }}</span>
          <span class="bms-audit-diff__old" data-test="diff-old">{{ formatDiffValue(item.oldValue, item.valueType) }}</span>
          <span class="bms-audit-diff__new" data-test="diff-new">{{ formatDiffValue(item.newValue, item.valueType) }}</span>
        </div>
      </div>

      <div
        v-if="showChain"
        class="bms-audit-diff__chain"
        data-test="chain-panel"
        :data-verified="chainVerified"
      >
        <span data-test="prev-hash">prev: {{ shortHash(prevHash) }}</span>
        <span data-test="record-hash">hash: {{ shortHash(recordHash) }}</span>
        <span data-test="chain-status">{{ chainText }}</span>
        <button v-if="chainVerified === false" type="button" data-test="locate" @click="emit('verify')">
          定位篡改记录
        </button>
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
