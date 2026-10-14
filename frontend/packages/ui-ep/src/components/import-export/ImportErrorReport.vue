<script setup lang="ts">
// 导入错误报告件（08_05）：汇总计数 + 错误行明细表（分页 / 截断提示）+ 下载错误明细。
// 供导入对话框与后续国际化文案导入导出（08_07）复用：只依赖 `ImportResult` 结构，不绑定导入流。
import { IMPORT_ERROR_PAGE_SIZE, paginateImportErrors, resolveImportSummary, type ImportResult } from '@bms/core'
import { ElButton, ElTable, ElTableColumn } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 导入结果。 */
  result?: ImportResult
  /** 当前页码（受控；缺省 1）。 */
  page?: number
  /** 每页行数（缺省 20）。 */
  pageSize?: number
  /** 业务中文名（表头提示用）。 */
  bizName?: string
  /** 是否下载中。 */
  downloading?: boolean
  /** 错误明细下载是否可用。 */
  downloadReady?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  result: undefined,
  page: 1,
  pageSize: IMPORT_ERROR_PAGE_SIZE,
  bizName: '',
  downloading: false,
  downloadReady: true,
})

const emit = defineEmits<{
  'update:page': [page: number]
  download: []
}>()

/** 汇总态（空数据 / 全部成功 / 部分失败）。 */
const summary = computed(() =>
  resolveImportSummary(props.result ?? { total: 0, successCount: 0, failCount: 0, errors: [] }),
)
/** 错误行分页视图。 */
const view = computed(() => paginateImportErrors(props.result?.errors ?? [], props.page, props.pageSize))
/** 是否全部成功（无错误行）。 */
const allSucceeded = computed(() => summary.value === 'success')
/** 总数（含截断部分）。 */
const total = computed(() => view.value.total)

const { state, setState } = useBaseDataState()
watch(
  summary,
  (value) => {
    setState(value === 'success' ? 'ready' : value === 'empty' ? 'empty' : 'ready')
  },
  { immediate: true },
)

/** 切换页码（夹取后上抛受控值）。 */
function goPage(page: number): void {
  if (page < 1 || page > view.value.pageCount || page === view.value.page) {
    return
  }
  emit('update:page', page)
}
</script>

<template>
  <div class="bms-import-error-report" data-test="error-report" :data-summary="summary" :data-state="state">
    <div class="bms-import-error-report__summary" data-test="error-summary">
      <div class="bms-import-error-report__stat" data-test="error-total">
        <span class="bms-import-error-report__value">{{ result?.total ?? 0 }}</span>
        <span class="bms-import-error-report__label">总行数</span>
      </div>
      <div class="bms-import-error-report__stat" data-test="error-success" data-tone="success">
        <span class="bms-import-error-report__value">{{ result?.successCount ?? 0 }}</span>
        <span class="bms-import-error-report__label">成功行数</span>
      </div>
      <div
        class="bms-import-error-report__stat"
        data-test="error-fail"
        :data-tone="summary === 'warning' ? 'danger' : 'normal'"
      >
        <span class="bms-import-error-report__value">{{ result?.failCount ?? 0 }}</span>
        <span class="bms-import-error-report__label">失败行数</span>
      </div>
    </div>

    <p v-if="allSucceeded" class="bms-import-error-report__ok" data-test="error-empty">
      <slot name="empty">全部导入成功</slot>
    </p>

    <template v-else>
      <div class="bms-import-error-report__table" data-test="error-table">
        <el-table :data="view.rows" size="small" border max-height="320">
          <el-table-column label="行号" width="90">
            <template #default="{ row }">
              <span :data-test="`error-row-${row.row}`" data-test-role="error-row-number">{{ row.row }}</span>
            </template>
          </el-table-column>
          <el-table-column label="列 / 字段" width="140">
            <template #default="{ row }">
              <span :data-column="row.column || undefined">{{ row.column ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="原因" />
        </el-table>
      </div>

      <p v-if="view.truncated" class="bms-import-error-report__truncated" data-test="error-truncated">
        仅展示前 {{ view.rows.length }} 行（共 {{ total }} 行），请下载完整明细
      </p>

      <div v-if="view.pageCount > 1" class="bms-import-error-report__pager" data-test="error-page">
        <el-button link data-test="error-prev" :disabled="view.page <= 1" @click="goPage(view.page - 1)">
          上一页
        </el-button>
        <span class="bms-import-error-report__page-current" data-test="error-page-current">
          {{ view.page }} / {{ view.pageCount }}
        </span>
        <el-button
          link
          data-test="error-next"
          :disabled="view.page >= view.pageCount"
          @click="goPage(view.page + 1)"
        >
          下一页
        </el-button>
      </div>
    </template>

    <footer class="bms-import-error-report__footer">
      <slot name="footer">
        <el-button
          type="primary"
          data-test="error-download"
          :disabled="downloading || !downloadReady"
          @click="emit('download')"
        >
          下载错误明细
        </el-button>
      </slot>
    </footer>
  </div>
</template>

<style scoped>
.bms-import-error-report {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

/* 结果汇总三宫格（总行数 / 成功 / 失败；数值强调）。 */
.bms-import-error-report__summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--bms-space-3);
}

.bms-import-error-report__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--bms-space-1);
  padding: var(--bms-space-3);
  background: var(--bms-import-summary-bg);
  border-radius: var(--bms-radius-md);
}

.bms-import-error-report__value {
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-lg);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.bms-import-error-report__stat[data-tone='success'] .bms-import-error-report__value {
  color: var(--bms-color-success);
}

.bms-import-error-report__stat[data-tone='danger'] .bms-import-error-report__value {
  color: var(--bms-color-danger);
}

.bms-import-error-report__label {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-import-error-report__ok {
  margin: 0;
  color: var(--bms-color-success);
  text-align: center;
}

.bms-import-error-report__table {
  min-width: 0;
}

/* 明细表经 `--el-table-*` 映射对齐令牌。 */
.bms-import-error-report__table :deep(.el-table__header-wrapper th) {
  background: var(--bms-table-header-bg);
}

.bms-import-error-report__table :deep(.el-table__body tr:hover > td) {
  background: var(--bms-table-row-hover-bg);
}

.bms-import-error-report__truncated {
  margin: 0;
  padding: var(--bms-space-2);
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-warning-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-import-error-report__pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--bms-space-2);
}

.bms-import-error-report__page-current {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  font-variant-numeric: tabular-nums;
}

.bms-import-error-report__footer {
  display: flex;
  justify-content: flex-end;
}
</style>
