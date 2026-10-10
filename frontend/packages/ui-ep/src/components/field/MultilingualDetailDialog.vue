<script setup lang="ts">
// 多语言明细弹框件（06_08）：独立可复用的语言明细编辑弹框。
// 明细表（语言 / 文案两列，行内编辑）+ 系统默认语言与必填语言标记 + 语言关键字与
// 「仅看缺失 / 仅看已填」本地筛选 + 行内缺省回退提示；确定回写、取消丢弃（草稿语义由宿主持有）。
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
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

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

const keyword = ref('')
const mode = ref<LocaleFilterMode>('all')
/** 关键字输入件投影（焦点 / 组合态语义经输入链承载）。 */
const keywordInput = useBaseInput<string>({ value: '' })

watch(keyword, (next) => keywordInput.setValue(next))

const filteredRows = computed(() => filterLocaleRows(props.rows, { keyword: keyword.value, mode: mode.value }))

const filledCount = computed(() => props.rows.filter((row) => !row.missing).length)

function onInput(code: string, event: Event): void {
  emit('edit', code, (event.target as HTMLInputElement | HTMLTextAreaElement).value)
}

function fallbackOf(row: LocaleRow): string {
  if (!row.missing) {
    return ''
  }
  const source = props.rows.find((item) => item.code === (row.code === props.defaultCode ? props.requiredCode : props.defaultCode))
  const text = source === undefined || source.value.trim() === '' ? '' : source.value.trim()
  return text === '' ? '' : `${I18N_FALLBACK_PREFIX}${text}`
}
</script>

<template>
  <div v-if="visible" class="bms-multilingual-detail" data-test="multilingual-detail">
    <div class="bms-multilingual-detail__panel" role="dialog" :aria-label="title">
      <header class="bms-multilingual-detail__header">
        <span class="bms-multilingual-detail__title">{{ title }}</span>
        <span class="bms-multilingual-detail__count" data-test="multilingual-detail-count">
          已填 {{ filledCount }} / {{ rows.length }}
        </span>
      </header>
      <p class="bms-multilingual-detail__hint">{{ I18N_DETAIL_HINT }}</p>
      <div class="bms-multilingual-detail__filter">
        <input
          v-model="keyword"
          class="bms-multilingual-detail__keyword"
          data-test="multilingual-detail-keyword"
          placeholder="语言关键字"
          @focus="keywordInput.focus()"
          @blur="keywordInput.blur()"
        />
        <button
          v-for="item in (['all', 'missing', 'filled'] as LocaleFilterMode[])"
          :key="item"
          type="button"
          class="bms-multilingual-detail__filter-item"
          :data-active="mode === item"
          :data-test="`multilingual-detail-filter-${item}`"
          @click="mode = item"
        >
          {{ item === 'all' ? '全部' : item === 'missing' ? '仅看缺失' : '仅看已填' }}
        </button>
      </div>
      <ul class="bms-multilingual-detail__rows">
        <li
          v-for="row in filteredRows"
          :key="row.code"
          class="bms-multilingual-detail__row"
          :dir="row.rtl ? 'rtl' : 'ltr'"
          :data-code="row.code"
        >
          <div class="bms-multilingual-detail__meta">
            <span class="bms-multilingual-detail__locale">{{ row.code }}</span>
            <span class="bms-multilingual-detail__name">{{ row.name }}</span>
            <span v-if="row.isRequired" class="bms-multilingual-detail__tag" data-test="multilingual-detail-required">
              {{ I18N_REQUIRED_TAG_TEXT }}
            </span>
            <span v-if="row.isDefault" class="bms-multilingual-detail__tag" data-test="multilingual-detail-default">
              {{ I18N_DEFAULT_TAG_TEXT }}
            </span>
            <span v-if="row.missing" class="bms-multilingual-detail__tag bms-multilingual-detail__tag--missing">
              {{ I18N_ROW_MISSING_TEXT }}
            </span>
          </div>
          <input
            v-if="!multiline"
            class="bms-multilingual-detail__input"
            :data-test="`multilingual-detail-input-${row.code}`"
            :value="row.value"
            :maxlength="maxLength"
            @input="onInput(row.code, $event)"
          />
          <textarea
            v-else
            class="bms-multilingual-detail__input"
            :data-test="`multilingual-detail-input-${row.code}`"
            :value="row.value"
            :maxlength="maxLength"
            rows="3"
            @input="onInput(row.code, $event)"
          ></textarea>
          <p v-if="fallbackOf(row) !== ''" class="bms-multilingual-detail__fallback">{{ fallbackOf(row) }}</p>
        </li>
        <li v-if="filteredRows.length === 0" class="bms-multilingual-detail__empty" data-test="multilingual-detail-empty">
          {{ I18N_DETAIL_EMPTY_TEXT }}
        </li>
      </ul>
      <footer class="bms-multilingual-detail__footer">
        <button type="button" class="bms-multilingual-detail__action" data-test="multilingual-detail-cancel" @click="emit('cancel')">
          取消
        </button>
        <button
          type="button"
          class="bms-multilingual-detail__action"
          data-test="multilingual-detail-confirm"
          @click="emit('confirm')"
        >
          确定
        </button>
      </footer>
    </div>
  </div>
</template>
