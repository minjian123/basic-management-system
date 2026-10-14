<script setup lang="ts">
// 审计差异查看（07_03）：筛选区 + 变更记录列表 + 字段级旧值→新值类型感知渲染 + 脱敏展示 + 链字段与校验结果。
import { ElButton, ElDatePicker, ElDrawer, ElInput, ElOption, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { computed, ref, watch } from 'vue'

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

/** 筛选条件。 */
export interface AuditFilter {
  /** 表名。 */
  tableName?: string
  /** 记录 ID。 */
  recordId?: string
  /** 操作人。 */
  operator?: string
  /** 时间范围（分片键，必填）。 */
  range?: [string, string] | null
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
  /** 表名候选（筛选区）。 */
  tableOptions?: string[]
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
  tableOptions: () => [],
  degradeText: '审计数据未就绪（占位）',
})

const emit = defineEmits<{
  query: [filter: AuditFilter]
  select: [record: AuditRecord]
  verify: [id?: string]
  'update:page': [page: number]
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

/** 筛选条件（受控于组件内部，查询时上抛）。 */
const filter = ref<AuditFilter>({ tableName: '', recordId: '', operator: '', range: null })

/** 时间范围为分片键、必填：缺失时禁用查询。 */
const rangeMissing = computed(() => filter.value.range === null || filter.value.range === undefined)

const showChain = computed(
  () => props.prevHash !== '' || props.recordHash !== '' || props.chainVerified !== undefined,
)

/** 详情抽屉显隐（选中记录时展开：有字段差异或链字段即视为已选中）。 */
const drawerVisible = ref(props.diff.length > 0 || showChain.value)
watch(
  () => [props.diff, showChain.value] as const,
  ([next, hasChain]) => {
    if (next.length > 0 || hasChain) {
      drawerVisible.value = true
    }
  },
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

/** 链状态标签语义色。 */
function chainTagType(status: AuditChainStatus | undefined): 'success' | 'danger' | 'info' {
  if (status === 'valid') {
    return 'success'
  }
  if (status === 'invalid') {
    return 'danger'
  }
  return 'info'
}

/** 链状态文案。 */
function chainLabel(status: AuditChainStatus | undefined): string {
  if (status === 'valid') {
    return '正常'
  }
  if (status === 'invalid') {
    return '篡改'
  }
  return '未校验'
}

function shortHash(hash: string): string {
  return hash === '' ? '' : `${hash.slice(0, 8)}…`
}

/** 查询（分片键缺失时不发起）。 */
function onQuery(): void {
  if (rangeMissing.value) {
    return
  }
  emit('query', { ...filter.value })
}

/** 重置筛选条件。 */
function onReset(): void {
  filter.value = { tableName: '', recordId: '', operator: '', range: null }
}

/** 行点击（打开详情抽屉并上抛选中）。 */
function onRowClick(record: AuditRecord): void {
  drawerVisible.value = true
  emit('select', record)
}
</script>

<template>
  <div class="bms-audit-diff" :data-ready="placeholder.ready.value" :data-degraded="placeholder.degraded.value">
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-audit-diff__toolbar" data-test="toolbar">
        <el-select v-model="filter.tableName" class="bms-audit-diff__filter" clearable placeholder="表名" size="small">
          <el-option v-for="name in tableOptions" :key="name" :label="name" :value="name" />
        </el-select>
        <el-input v-model="filter.recordId" class="bms-audit-diff__filter" clearable placeholder="记录 ID" size="small" />
        <el-input v-model="filter.operator" class="bms-audit-diff__filter" clearable placeholder="操作人" size="small" />
        <el-date-picker
          v-model="filter.range"
          type="daterange"
          size="small"
          range-separator="~"
          start-placeholder="开始"
          end-placeholder="结束"
          value-format="YYYY-MM-DD"
        />
        <el-button size="small" type="primary" data-test="query" :disabled="rangeMissing" @click="onQuery">查询</el-button>
        <el-button size="small" data-test="reset" @click="onReset">重置</el-button>
        <el-button size="small" data-test="verify" @click="emit('verify')">链校验</el-button>
        <span v-if="rangeMissing" class="bms-audit-diff__hint" data-test="range-hint">
          时间范围（分片键）必填
        </span>
      </div>

      <el-table
        v-if="records.length > 0"
        class="bms-audit-diff__table"
        :data="records"
        size="small"
        border
        data-test="records"
        @row-click="onRowClick"
      >
        <el-table-column label="表名" min-width="140">
          <template #default="{ row }">
            <span :data-test="`record-${row.id}`" :data-chain="row.chainStatus ?? 'unknown'">
              {{ row.tableName }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="记录 ID" min-width="110">
          <template #default="{ row }">
            <span data-test="record-id">{{ row.recordId }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变更字段数" width="110">
          <template #default="{ row }">
            <span data-test="field-count">{{ row.fields ?? 0 }} 项</span>
          </template>
        </el-table-column>
        <el-table-column label="操作人" min-width="110">
          <template #default="{ row }">
            <span data-test="operator">{{ row.operator }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" min-width="170">
          <template #default="{ row }">
            <span data-test="created-at">{{ row.createdAt }}</span>
          </template>
        </el-table-column>
        <el-table-column label="链状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="chainTagType(row.chainStatus)">
              {{ chainLabel(row.chainStatus) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="bms-audit-diff__empty" data-test="empty">
        <slot name="empty">暂无变更记录</slot>
      </div>

      <div class="bms-audit-diff__footer" data-test="footer">
        <span data-test="total">共 {{ total }} 条</span>
        <el-button size="small" data-test="prev" :disabled="page <= 1" @click="emit('update:page', page - 1)">
          上一页
        </el-button>
        <span data-test="page">{{ page }}</span>
        <el-button size="small" data-test="next" @click="emit('update:page', page + 1)">下一页</el-button>
      </div>

      <el-drawer
        v-model="drawerVisible"
        class="bms-audit-diff__drawer"
        title="变更差异"
        size="620px"
        data-test="diff-drawer"
      >
        <div v-if="diff.length > 0" class="bms-audit-diff__diff" data-test="diff-panel">
          <div class="bms-audit-diff__field is-head">
            <span class="bms-audit-diff__label">字段</span>
            <span class="bms-audit-diff__old">变更前</span>
            <span class="bms-audit-diff__new">变更后</span>
          </div>
          <div
            v-for="item in diff"
            :key="item.field"
            class="bms-audit-diff__field"
            :data-test="`diff-${item.field}`"
            :data-change="diffKind(item.oldValue, item.newValue)"
          >
            <span class="bms-audit-diff__label" data-test="diff-field">{{ item.label ?? item.field }}</span>
            <span class="bms-audit-diff__old" data-test="diff-old">
              {{ formatDiffValue(item.oldValue, item.valueType) }}
            </span>
            <span class="bms-audit-diff__new" data-test="diff-new">
              {{ formatDiffValue(item.newValue, item.valueType) }}
            </span>
          </div>
        </div>

        <div v-if="showChain" class="bms-audit-diff__chain" data-test="chain-panel" :data-verified="chainVerified">
          <span class="bms-audit-diff__hash" data-test="prev-hash">prev: {{ shortHash(prevHash) }}</span>
          <span class="bms-audit-diff__hash" data-test="record-hash">hash: {{ shortHash(recordHash) }}</span>
          <span data-test="chain-status">{{ chainText }}</span>
          <el-button
            v-if="chainVerified === false"
            size="small"
            type="primary"
            data-test="locate"
            @click="emit('verify')"
          >
            定位篡改记录
          </el-button>
        </div>
      </el-drawer>
    </template>
  </div>
</template>

<style scoped>
.bms-audit-diff {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  color: var(--bms-color-text);
}

.bms-audit-diff__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-audit-diff__filter {
  width: 140px;
}

.bms-audit-diff__hint {
  font-size: var(--bms-font-size-xs);
  color: var(--bms-color-warning);
}

.bms-audit-diff__table :deep(.el-table__header th) {
  background: var(--bms-table-header-bg);
  border-color: var(--bms-table-border);
}

.bms-audit-diff__table :deep(.el-table__row) {
  cursor: pointer;
}

.bms-audit-diff__table :deep(.el-table__row:hover td) {
  background: var(--bms-table-row-hover-bg);
}

.bms-audit-diff__empty {
  padding: var(--bms-space-6);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  text-align: center;
}

.bms-audit-diff__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--bms-space-2);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.bms-audit-diff__field {
  display: grid;
  grid-template-columns: 160px 1fr 1fr;
  gap: var(--bms-space-3);
  align-items: start;
  padding: var(--bms-space-2) 0;
  font-size: var(--bms-font-size-sm);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-audit-diff__field.is-head {
  font-weight: 600;
  color: var(--bms-color-text-secondary);
}

.bms-audit-diff__field[data-change='added'] .bms-audit-diff__new {
  color: var(--bms-diff-add-color);
  background: var(--bms-diff-add-bg);
}

.bms-audit-diff__field[data-change='removed'] .bms-audit-diff__old {
  color: var(--bms-diff-del-color);
  background: var(--bms-diff-del-bg);
}

.bms-audit-diff__field[data-change='modified'] .bms-audit-diff__old {
  color: var(--bms-diff-del-color);
  background: var(--bms-diff-del-bg);
}

.bms-audit-diff__field[data-change='modified'] .bms-audit-diff__new {
  color: var(--bms-diff-add-color);
  background: var(--bms-diff-add-bg);
}

.bms-audit-diff__label {
  color: var(--bms-color-text-secondary);
  word-break: break-all;
}

.bms-audit-diff__old,
.bms-audit-diff__new {
  padding: 0 var(--bms-space-1);
  border-radius: var(--bms-radius-sm);
  word-break: break-all;
}

.bms-audit-diff__chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-3);
  padding-top: var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
}

.bms-audit-diff__hash {
  font-family: var(--bms-font-family-mono);
  color: var(--bms-color-text-secondary);
}
</style>
