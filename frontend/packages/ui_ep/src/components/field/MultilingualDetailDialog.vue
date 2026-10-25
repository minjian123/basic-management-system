<script setup lang="ts">
// 多语言明细弹框件（06_08）：独立可复用的语言明细编辑弹框。
// 承载：`el-dialog`（弹框容器口径：宽度 / 遮罩 / 焦点 / Esc）+ `el-table` 两列（语言 / 文案，行内编辑）；
// 系统默认语言与必填语言标记 + 语言关键字与「仅看缺失 / 仅看已填」本地筛选 + 行内缺省回退提示（输入占位）；
// 确定回写、取消丢弃（草稿语义由宿主持有）+ 脏数据二次确认（放弃 / 继续编辑）。
import {
  I18N_DEFAULT_TAG_TEXT,
  I18N_DETAIL_EMPTY_TEXT,
  I18N_DETAIL_HINT,
  I18N_DETAIL_TITLE,
  I18N_FALLBACK_PREFIX,
  I18N_REQUIRED_TAG_TEXT,
  I18N_ROW_MISSING_TEXT,
  filterLocaleRows,
  type LocaleFilterMode,
  type LocaleRow,
} from '@bms/core'
import { ElButton, ElDialog, ElRadioButton, ElRadioGroup, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useConfirm } from '../../composables/useConfirm'
import TextInput from '../input/TextInput.vue'
import TextareaInput from '../input/TextareaInput.vue'

interface Props {
  /** 是否可见。 */
  visible: boolean
  /** 语言行（含语言标识 / 语言名 / 标记 / 缺失态）。 */
  rows: LocaleRow[]
  /** 必填语言标识（＝当前登录用户语言）。 */
  requiredCode: string
  /** 系统默认语言标识。 */
  defaultCode: string
  /** 是否多行形态（描述 / 正文）。 */
  multiline?: boolean
  /** 单条文案长度上限（Unicode 码点）。 */
  maxLength?: number
  /** 标题。 */
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  multiline: false,
  maxLength: 128,
  title: I18N_DETAIL_TITLE,
})

const emit = defineEmits<{
  /** 行内编辑（草稿；`code` 语言标识，`value` 文案）。 */
  edit: [code: string, value: string]
  /** 确定（草稿回写宿主）。 */
  confirm: []
  /** 取消（丢弃草稿）。 */
  cancel: []
}>()

const { confirm: askConfirm } = useConfirm()
const keyword = ref('')
const mode = ref<LocaleFilterMode>('all')
/** 弹框内草稿副本（用于脏数据判定与行内编辑回显）。 */
const draft = ref<Record<string, string>>({})

watch(
  () => props.rows,
  (next) => {
    const map: Record<string, string> = {}
    for (const row of next) {
      map[row.code] = row.value
    }
    draft.value = map
  },
  { immediate: true, deep: true },
)

/** 草稿是否已改动（与进入时快照比较）。 */
const draftChanged = computed(() => props.rows.some((row) => (draft.value[row.code] ?? row.value) !== row.value))

const filteredRows = computed(() =>
  filterLocaleRows(
    props.rows.map((row) => ({ ...row, value: draft.value[row.code] ?? row.value })),
    { keyword: keyword.value, mode: mode.value },
  ),
)

const filledCount = computed(() => props.rows.filter((row) => (draft.value[row.code] ?? row.value).trim() !== '').length)

/** 弹框可见性（双向：关闭时按脏数据拦截）。 */
const dialogVisible = computed({
  get: () => props.visible,
  set: (next: boolean) => {
    if (!next) {
      void requestCancel()
    }
  },
})

/**
 * 收窄 `el-table` 插槽行类型（`DefaultRow`）为契约行。
 *
 * @param row 插槽行。
 * @returns 契约行。
 */
function asRow(row: unknown): LocaleRow {
  return row as LocaleRow
}

/** 缺省回退提示（回退链首位有值者）。 */
function fallbackOf(row: LocaleRow): string {
  if ((draft.value[row.code] ?? row.value).trim() !== '') {
    return ''
  }
  const source = props.rows.find(
    (item) => item.code === (row.code === props.defaultCode ? props.requiredCode : props.defaultCode),
  )
  const text = source === undefined ? '' : (draft.value[source.code] ?? source.value).trim()
  return text === '' ? '' : `${I18N_FALLBACK_PREFIX}${text}`
}

/** 文案列输入占位（缺省回退提示改入占位，节点 §4/§10）。 */
function placeholderOf(row: LocaleRow): string {
  if (row.code === props.requiredCode) {
    return '必填语言文案（必填）'
  }
  const fallback = fallbackOf(row)
  return fallback === '' ? '可缺省' : fallback
}

/** 行内编辑（写入草稿并上抛）。 */
function onEdit(code: string, value: string): void {
  draft.value = { ...draft.value, [code]: value }
  emit('edit', code, value)
}

/**
 * 取消：有改动时二次确认（放弃 / 继续编辑）；确认放弃才真正关闭（节点 §4/§9）。
 */
async function requestCancel(): Promise<void> {
  if (draftChanged.value) {
    const discard = await askConfirm({
      content: '弹框内文案已修改，放弃这些改动？',
      confirmText: '放弃',
      cancelText: '继续编辑',
    })
    if (!discard) {
      return
    }
  }
  emit('cancel')
}

/** 确定：草稿回写宿主。 */
function onConfirm(): void {
  emit('confirm')
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    class="bms-multilingual-detail"
    :title="title"
    width="620px"
    :close-on-click-modal="false"
    data-test="multilingual-detail"
  >
    <p class="bms-multilingual-detail__hint">{{ I18N_DETAIL_HINT }}</p>

    <div class="bms-multilingual-detail__filter">
      <text-input
        v-model="keyword"
        class="bms-multilingual-detail__keyword"
        data-test="multilingual-detail-keyword"
        size="small"
        clearable
        placeholder="语言关键字"
      />
      <el-radio-group v-model="mode" size="small">
        <el-radio-button
          v-for="item in (['all', 'missing', 'filled'] as LocaleFilterMode[])"
          :key="item"
          :value="item"
          :data-test="`multilingual-detail-filter-${item}`"
        >
          {{ item === 'all' ? '全部' : item === 'missing' ? '仅看缺失' : '仅看已填' }}
        </el-radio-button>
      </el-radio-group>
      <span class="bms-multilingual-detail__count" data-test="multilingual-detail-count">
        已填 {{ filledCount }} / {{ rows.length }}
      </span>
    </div>

    <el-table :data="filteredRows" size="small" border max-height="320" class="bms-multilingual-detail__table">
      <el-table-column label="语言" width="220">
        <template #default="scope">
          <div class="bms-multilingual-detail__meta" :dir="scope.row.rtl ? 'rtl' : 'ltr'">
            <span class="bms-multilingual-detail__locale">{{ scope.row.code }}</span>
            <span class="bms-multilingual-detail__name">{{ scope.row.name }}</span>
            <el-tag
              v-if="scope.row.isRequired"
              class="bms-multilingual-detail__tag"
              size="small"
              type="success"
              data-test="multilingual-detail-required"
            >
              {{ I18N_REQUIRED_TAG_TEXT }}
            </el-tag>
            <el-tag
              v-if="scope.row.isDefault"
              class="bms-multilingual-detail__tag"
              size="small"
              type="info"
              data-test="multilingual-detail-default"
            >
              {{ I18N_DEFAULT_TAG_TEXT }}
            </el-tag>
            <el-tag
              v-if="(draft[scope.row.code] ?? scope.row.value).trim() === ''"
              class="bms-multilingual-detail__tag"
              size="small"
              type="warning"
            >
              {{ I18N_ROW_MISSING_TEXT }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="文案">
        <template #default="scope">
          <textarea-input
            v-if="multiline"
            :model-value="draft[scope.row.code] ?? scope.row.value"
            :data-test="`multilingual-detail-input-${scope.row.code}`"
            :placeholder="placeholderOf(asRow(scope.row))"
            :maxlength="maxLength"
            :rows="3"
            @update:model-value="(next: string) => onEdit(scope.row.code, next)"
          />
          <text-input
            v-else
            :model-value="draft[scope.row.code] ?? scope.row.value"
            :data-test="`multilingual-detail-input-${scope.row.code}`"
            :placeholder="placeholderOf(asRow(scope.row))"
            :maxlength="maxLength"
            @update:model-value="(next: string) => onEdit(scope.row.code, next)"
          />
        </template>
      </el-table-column>
      <template #empty>
        <span class="bms-multilingual-detail__empty" data-test="multilingual-detail-empty">{{ I18N_DETAIL_EMPTY_TEXT }}</span>
      </template>
    </el-table>

    <template #footer>
      <el-button data-test="multilingual-detail-cancel" @click="requestCancel">取消</el-button>
      <el-button type="primary" data-test="multilingual-detail-confirm" @click="onConfirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.bms-multilingual-detail__hint {
  margin: 0 0 var(--bms-space-2);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-multilingual-detail__filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-2);
}

.bms-multilingual-detail__keyword {
  width: 220px;
}

.bms-multilingual-detail__count {
  margin-left: auto;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-multilingual-detail__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-1);
}

.bms-multilingual-detail__locale {
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

.bms-multilingual-detail__name {
  color: var(--bms-color-text);
}

.bms-multilingual-detail__tag {
  background: var(--bms-i18n-marker-bg);
}

.bms-multilingual-detail__empty {
  color: var(--bms-color-text-secondary);
}

/* 明细表经 `--el-table-*` 映射对齐令牌。 */
.bms-multilingual-detail__table :deep(.el-table__header-wrapper th) {
  background: var(--bms-table-header-bg);
}

.bms-multilingual-detail__table :deep(.el-table__body tr:hover > td) {
  background: var(--bms-table-row-hover-bg);
}
</style>
