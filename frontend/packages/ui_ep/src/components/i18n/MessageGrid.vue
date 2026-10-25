<script setup lang="ts">
// 国际化文案网格（08_07）：由 I18nMessageEditor 异步懒加载的独立分包入口；
// `msg_key` × 多语言可编辑单元格 + 缺失高亮 + 停用列置灰 + 受控分页 + 超阈值切虚拟滚动。
import type { I18nLocaleItem, I18nMessageItem } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import { useBaseMessageCatalog } from '../../composables/useBaseMessageCatalog'
import VirtualListContainer from '../container/VirtualListContainer.vue'

interface Props {
  /** 语言清单。 */
  locales?: readonly I18nLocaleItem[]
  /** 文案行。 */
  messages?: readonly I18nMessageItem[]
  /** 聚焦语言（仅显示该语言列）。 */
  activeLocale?: string
  /** 当前页码（受控）。 */
  page?: number
  /** 每页行数。 */
  pageSize?: number
  /** 总页数。 */
  pageCount?: number
  /** 总条数。 */
  total?: number
  /** 是否虚拟滚动。 */
  virtualized?: boolean
  /** 已修改行的键。 */
  modifiedKeys?: readonly string[]
  /** 是否显示停用语言列。 */
  showDisabledLocales?: boolean
  /** 禁用（占位 / 无权）。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  locales: () => [],
  messages: () => [],
  activeLocale: '',
  page: 1,
  pageSize: 50,
  pageCount: 1,
  total: 0,
  virtualized: false,
  modifiedKeys: () => [],
  showDisabledLocales: false,
  disabled: false,
})

const emit = defineEmits<{
  'cell-change': [payload: { key: string; locale: string; value: string }]
  'remove-key': [key: string]
  'update:page': [value: number]
  'update:pageSize': [value: number]
  'add-key': []
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { catalog } = useBaseMessageCatalog()
const { state, setState } = useBaseDataState()

/** 单元格编辑草稿（key → locale 值），失焦提交前按内容比较。 */
const drafts = ref<Record<string, string>>({})

watch(
  () => props.messages.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

/** 展示列（停用列置灰仍占位，可由 `showDisabledLocales` 隐藏；聚焦语言过滤其他列）。 */
const columns = computed<I18nLocaleItem[]>(() => {
  const base = props.showDisabledLocales
    ? [...props.locales]
    : props.locales.filter((item) => item.status === 'enabled')
  return props.activeLocale === '' ? base : base.filter((item) => item.code === props.activeLocale)
})

/**
 * 行是否被修改。
 *
 * @param key 文案键。
 */
function isModified(key: string): boolean {
  return props.modifiedKeys.includes(key)
}

/**
 * 取单元格草稿值（无草稿回落到行值）。
 *
 * @param row 文案行。
 * @param code 语言标识。
 */
function cellValue(row: I18nMessageItem, code: string): string {
  const draft = drafts.value[`${row.key}\u0000${code}`]
  return draft ?? row.values[code] ?? ''
}

/**
 * 记录单元格草稿。
 *
 * @param row 文案行。
 * @param code 语言标识。
 * @param value 输入值。
 */
function onInput(row: I18nMessageItem, code: string, value: string): void {
  drafts.value = { ...drafts.value, [`${row.key}\u0000${code}`]: value }
}

/**
 * 提交草稿（变更 / 失焦 / 回车；**未经编辑（无草稿）不上抛**，提交后清草稿避免重复上报）。
 *
 * @param row 文案行。
 * @param code 语言标识。
 */
function commit(row: I18nMessageItem, code: string): void {
  const key = `${row.key}\u0000${code}`
  const draft = drafts.value[key]
  if (draft === undefined) {
    return
  }
  const next = { ...drafts.value }
  delete next[key]
  drafts.value = next
  emit('cell-change', { key: row.key, locale: code, value: draft })
}

/**
 * 语言是否停用（置灰不可编辑）。
 *
 * @param code 语言标识。
 */
function isDisabledColumn(code: string): boolean {
  return props.locales.find((item) => item.code === code)?.status !== 'enabled'
}

/**
 * 跳转页码（受控：只上抛）。
 *
 * @param page 目标页码。
 */
function goPage(page: number): void {
  emit('update:page', page)
}

/** 页面内可视化行（虚拟滚动模式由容器接管）。 */
const showPager = computed(() => !props.virtualized && props.total > props.pageSize)
</script>

<template>
  <div
    class="bms-message-grid"
    data-test="message-grid"
    data-subpackage="i18n"
    :data-state="state"
    :data-source="catalog.identifier"
    :data-virtual="virtualized"
  >
    <p v-if="messages.length === 0" data-test="grid-empty">
      <slot name="empty">暂无文案数据</slot>
    </p>

    <template v-else>
      <VirtualListContainer v-if="virtualized" data-test="grid-virtual" :items="messages" :item-height="40" height="420px">
        <template #default="{ item }">
          <table class="bms-message-grid__table">
            <tbody>
              <tr :data-test="`message-${(item as I18nMessageItem).key}`">
                <td data-test="message-key">
                  {{ (item as I18nMessageItem).key }}
                  <button
                    type="button"
                    :data-test="`remove-${(item as I18nMessageItem).key}`"
                    :disabled="disabled"
                    @click="emit('remove-key', (item as I18nMessageItem).key)"
                  >
                    删除
                  </button>
                </td>
                <td
                  v-for="locale in columns"
                  :key="locale.code"
                  :data-test="`cell-wrap-${(item as I18nMessageItem).key}-${locale.code}`"
                  :data-missing="(item as I18nMessageItem).missing.includes(locale.code) || undefined"
                  :data-disabled="isDisabledColumn(locale.code) || undefined"
                >
                  <input
                    type="text"
                    :value="cellValue(item as I18nMessageItem, locale.code)"
                    :disabled="disabled || isDisabledColumn(locale.code)"
                    :data-test="`cell-${(item as I18nMessageItem).key}-${locale.code}`"
                    @input="onInput(item as I18nMessageItem, locale.code, ($event.target as HTMLInputElement).value)"
                    @change="commit(item as I18nMessageItem, locale.code)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </VirtualListContainer>

      <table v-else class="bms-message-grid__table">
        <thead>
          <tr>
            <th>msg_key</th>
            <th v-for="locale in columns" :key="locale.code" :data-test="`column-${locale.code}`">
              {{ locale.code }}
              <span v-if="isDisabledColumn(locale.code)" :data-test="`data-column-disabled-${locale.code}`">（停用）</span>
            </th>
            <th>
              <button type="button" data-test="add-key" :disabled="disabled" @click="emit('add-key')">新增 key</button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in messages"
            :key="row.key"
            :data-test="`message-${row.key}`"
            :data-modified="isModified(row.key) || undefined"
          >
            <td data-test="message-key">
              {{ row.key }}
              <span v-if="isModified(row.key)" :data-test="`cell-modified-${row.key}`">已修改</span>
              <button type="button" :data-test="`remove-${row.key}`" :disabled="disabled" @click="emit('remove-key', row.key)">
                删除
              </button>
            </td>
            <td
              v-for="locale in columns"
              :key="locale.code"
              :data-test="`cell-wrap-${row.key}-${locale.code}`"
              :data-missing="row.missing.includes(locale.code) || undefined"
              :data-disabled="isDisabledColumn(locale.code) || undefined"
            >
              <input
                type="text"
                :value="cellValue(row, locale.code)"
                :disabled="disabled || isDisabledColumn(locale.code)"
                :title="cellValue(row, locale.code)"
                :data-test="`cell-${row.key}-${locale.code}`"
                @input="onInput(row, locale.code, ($event.target as HTMLInputElement).value)"
                @change="commit(row, locale.code)"
              />
              <span v-if="row.missing.includes(locale.code)" :data-test="`cell-missing-${row.key}-${locale.code}`">缺失</span>
            </td>
            <td />
          </tr>
        </tbody>
      </table>

      <div v-if="showPager" class="bms-message-grid__pager" data-test="grid-pager">
        <span data-test="grid-total">共 {{ total }} 条</span>
        <button type="button" data-test="grid-prev" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <span data-test="grid-page-current">{{ page }} / {{ pageCount }}</span>
        <button type="button" data-test="grid-next" :disabled="page >= pageCount" @click="goPage(page + 1)">下一页</button>
        <button type="button" data-test="grid-smaller" @click="emit('update:pageSize', 20)">每页 20</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-message-grid__table {
  width: 100%;
  border-collapse: collapse;
}

.bms-message-grid__table th,
.bms-message-grid__table td {
  border: 1px solid var(--bms-color-border);
  padding: 2px 6px;
  text-align: left;
}

.bms-message-grid__table td[data-missing] {
  background: var(--bms-color-warning-bg);
}

.bms-message-grid__table td[data-disabled] {
  background: var(--bms-color-fill);
  color: var(--bms-color-text-secondary);
}

.bms-message-grid__pager {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}
</style>
