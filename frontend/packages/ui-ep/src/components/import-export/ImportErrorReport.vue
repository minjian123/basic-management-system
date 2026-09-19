<script setup lang="ts">
// 导入错误报告件（08_05）：汇总计数 + 错误行明细表（分页 / 截断提示）+ 下载错误明细。
// 供导入对话框与后续国际化文案导入导出（08_07）复用：只依赖 `ImportResult` 结构，不绑定导入流。
import { IMPORT_ERROR_PAGE_SIZE, paginateImportErrors, resolveImportSummary, type ImportResult } from '@bms/core'
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
      <span data-test="error-total">总 {{ result?.total ?? 0 }}</span>
      <span data-test="error-success">成功 {{ result?.successCount ?? 0 }}</span>
      <span data-test="error-fail" :data-warning="summary === 'warning' || undefined">
        失败 {{ result?.failCount ?? 0 }}
      </span>
    </div>

    <p v-if="allSucceeded" class="bms-import-error-report__ok" data-test="error-empty">
      <slot name="empty">全部导入成功</slot>
    </p>

    <template v-else>
      <table class="bms-import-error-report__table" data-test="error-table">
        <thead>
          <tr>
            <th>行号</th>
            <th>列 / 字段</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in view.rows" :key="`${item.row}-${item.column ?? ''}`" :data-test="`error-row-${item.row}`">
            <td data-test="error-row-number">{{ item.row }}</td>
            <td :data-column="item.column || undefined">{{ item.column ?? '—' }}</td>
            <td>{{ item.message }}</td>
          </tr>
        </tbody>
      </table>

      <p v-if="view.truncated" class="bms-import-error-report__truncated" data-test="error-truncated">
        仅展示前 {{ view.rows.length }} 行（共 {{ total }} 行），请下载完整明细
      </p>

      <div v-if="view.pageCount > 1" class="bms-import-error-report__pager" data-test="error-page">
        <button type="button" data-test="error-prev" :disabled="view.page <= 1" @click="goPage(view.page - 1)">
          上一页
        </button>
        <span data-test="error-page-current">{{ view.page }} / {{ view.pageCount }}</span>
        <button
          type="button"
          data-test="error-next"
          :disabled="view.page >= view.pageCount"
          @click="goPage(view.page + 1)"
        >
          下一页
        </button>
      </div>
    </template>

    <footer class="bms-import-error-report__footer">
      <slot name="footer">
        <button
          type="button"
          data-test="error-download"
          :disabled="downloading || !downloadReady"
          @click="emit('download')"
        >
          下载错误明细
        </button>
      </slot>
    </footer>
  </div>
</template>
