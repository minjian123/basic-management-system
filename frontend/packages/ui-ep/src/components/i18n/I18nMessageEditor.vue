<script setup lang="ts">
// 国际化文案编辑器（08_07）：契约承接 08_01_02 冻结形状；页签装配（语言管理 / 语言包维护）、工具栏、批量保存与缓存失效、脏数据拦截、导入导出接线。文案网格独立分包懒加载。
import type {
  BaseAccess,
  BaseNotice,
  I18nFilter,
  I18nLocaleItem,
  I18nMessageItem,
  MessageJobs,
  SaveResult,
} from '@bms/core'
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseLocale } from '../../composables/useBaseLocale'
import { useBaseMessageCatalog } from '../../composables/useBaseMessageCatalog'
import { useConfirm } from '../../composables/useConfirm'
import ExportButton from '../import-export/ExportButton.vue'
import ImportDialog from '../import-export/ImportDialog.vue'
import LocaleList from './LocaleList.vue'
import MessageFilter from './MessageFilter.vue'

// 文案网格独立分包（懒加载入口；不入插件根出口，否则分包退化）。
const MessageGrid = defineAsyncComponent(() => import('./MessageGrid.vue'))

/** 语言项（对外类型，承接 08_01_02 冻结形状）。 */
export interface I18nLocale {
  /** 语言标识（如 `zh-CN`）。 */
  code: string
  /** 语言名。 */
  name: string
  /** 是否从右到左。 */
  rtl?: boolean
  /** 状态。 */
  status: 'enabled' | 'disabled'
}

/** 文案行（对外类型）。 */
export interface I18nMessageRow {
  /** 文案键。 */
  key: string
  /** 各语言值。 */
  values: Record<string, string>
  /** 缺失翻译的语言标识。 */
  missing?: string[]
}

/** 变更载荷。 */
export interface I18nChangePayload {
  /** 变更类型。 */
  kind: 'message' | 'key' | 'locale'
  /** 变更值。 */
  value: unknown
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 语言清单。 */
  locales?: I18nLocale[]
  /** 文案行。 */
  messages?: I18nMessageRow[]
  /** 聚焦语言（仅显示该语言列）。 */
  activeLocale?: string
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 加载中。 */
  loading?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 注入的处理函数集（未注入即占位；仅事件上抛）。 */
  jobs?: MessageJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 当前页码（下发面）。 */
  page?: number
  /** 每页行数（下发面）。 */
  pageSize?: number
  /** 筛选条件下发面。 */
  filter?: Partial<I18nFilter>
  /** 是否显示停用语言列。 */
  showDisabledLocales?: boolean
  /** 默认语言（不可停用）。 */
  defaultLocale?: string
  /** 宿主下发的已修改行键（与投影取并集）。 */
  modifiedKeys?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  locales: () => [],
  messages: () => [],
  activeLocale: '',
  dirty: false,
  loading: false,
  degradeText: '国际化文案未就绪（占位）',
  jobs: undefined,
  access: undefined,
  notice: undefined,
  page: undefined,
  pageSize: undefined,
  filter: undefined,
  showDisabledLocales: false,
  defaultLocale: 'zh-CN',
  modifiedKeys: () => [],
})

const emit = defineEmits<{
  change: [payload: I18nChangePayload]
  save: []
  'invalidate-cache': []
  'add-key': []
  'remove-key': [key: string]
  'add-locale': []
  'toggle-locale': [payload: { code: string; enabled: boolean }]
  export: []
  import: []
  retry: []
  'update:tab': [tab: MessageTab]
  saved: [result: SaveResult]
  failed: [payload: { message: string; code: number }]
  'cache-invalidated': [payload: { ok: boolean }]
  'messages-reloaded': [payload: { revision: number }]
  'page-change': [page: number]
  'filter-change': [filter: I18nFilter]
}>()

/** 页签。 */
export type MessageTab = 'locales' | 'messages'

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const catalogApi = useBaseMessageCatalog({
  ready: props.ready,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
  defaultLocale: props.defaultLocale,
  showDisabledLocales: props.showDisabledLocales,
  page: props.page,
  pageSize: props.pageSize,
  activeLocale: props.activeLocale,
  filter: props.filter,
})
const { locale, setLocale } = useBaseLocale()
const { confirm } = useConfirm()

/** 当前页签（受控：点击只上抛；未接线回退内部态）。 */
const innerTab = ref<MessageTab>('messages')
/** 导入对话框显隐。 */
const importVisible = ref(false)
/** 导出参数快照（由核心派生，宿主也可覆盖）。 */
const exportParams = computed(() => catalogApi.exportParams.value)

watch(
  () => props.ready,
  (next) => catalogApi.setReady(next),
)
watch(
  () => props.activeLocale,
  (next) => {
    if (next !== '') {
      catalogApi.setActiveLocale(next)
      setLocale(next)
    }
  },
  { immediate: true },
)
watch(
  () => props.jobs,
  (next) => catalogApi.setJobs(next ?? {}),
)
// 宿主下发面同步进内核（同一份数据两处一致：渲染用 props，编排用内核；下发即视为已保存基线）。
watch(
  () => [props.locales, props.messages] as const,
  () => {
    catalogApi.catalog.applySnapshot({ locales: props.locales, messages: props.messages })
  },
  { immediate: true },
)

/** 生效语言清单（宿主下发优先，否则用投影列集）。 */
const effectiveLocales = computed<I18nLocaleItem[]>(() => {
  if (props.locales.length > 0) {
    return props.locales.map((item) => ({ code: item.code, name: item.name, rtl: item.rtl ?? false, status: item.status }))
  }
  return catalogApi.columns.value
})

/** 生效文案行（注入编排通路时用投影可见行以承载本地筛选；纯事件用法回落宿主下发面）。 */
const effectiveMessages = computed<I18nMessageItem[]>(() => {
  if (props.messages.length > 0 && !hasJobs.value) {
    return props.messages.map((row) => ({ key: row.key, values: { ...row.values }, missing: row.missing ?? [] }))
  }
  return catalogApi.visibleMessages.value
})

/** 生效筛选条件（宿主下发优先）。 */
const effectiveFilter = computed<I18nFilter>(() => catalogApi.filter.value)

/** 生效已修改键（宿主下发与投影取并集）。 */
const effectiveModifiedKeys = computed(() => {
  const merged = new Set<string>([...props.modifiedKeys, ...catalogApi.modifiedKeys.value])
  return [...merged]
})

/** 是否脏（宿主下发与投影合并）。 */
const isDirty = computed(() => props.dirty || catalogApi.dirty.value)

/** 是否存在注入的编排通路（决定点击是否驱动真实编排）。 */
const hasJobs = computed(() => props.jobs !== undefined && Object.keys(props.jobs).length > 0)

/** 保存结果提示（成功即时生效；缓存失效未完成时降级提示）。 */
const saveHint = ref('')

/**
 * 切换页签（受控：先上抛；有未保存变更时二次确认）。
 *
 * @param tab 目标页签。
 */
async function switchTab(tab: MessageTab): Promise<void> {
  if (tab === innerTab.value) {
    return
  }
  if (isDirty.value) {
    const accepted = await confirm({ content: '存在未保存的文案变更，切换页签将丢失这些修改，是否继续？', danger: true })
    if (!accepted) {
      return
    }
    catalogApi.resetDirty()
  }
  innerTab.value = tab
  emit('update:tab', tab)
}

/**
 * 语言启停切换（承接 08_01_02 冻结事件形状）。
 *
 * @param item 语言项。
 */
function toggleLocale(item: I18nLocale): void {
  const enabled = item.status !== 'enabled'
  emit('toggle-locale', { code: item.code, enabled })
  if (hasJobs.value) {
    const check = catalogApi.toggleLocale(item.code, enabled)
    if (!check.valid) {
      emit('failed', { message: check.message, code: check.code })
    }
  }
}

/** 保存：先上抛既有事件，再按需驱动真实编排。 */
async function onSave(): Promise<void> {
  emit('save')
  if (!hasJobs.value) {
    return
  }
  const result = await catalogApi.save()
  if (result === undefined) {
    saveHint.value = catalogApi.errorMessage.value
    emit('failed', { message: catalogApi.errorMessage.value, code: catalogApi.errorCode.value })
    return
  }
  saveHint.value = result.cacheInvalidated ? '保存成功，文案已即时生效' : '保存成功，但语言包缓存失效未完成（将按短 TTL 兜底）'
  emit('saved', result)
  emit('cache-invalidated', { ok: result.cacheInvalidated })
  if (result.reloaded) {
    emit('messages-reloaded', { revision: catalogApi.messagesRevision.value })
  }
}

/** 缓存失效：先上抛既有事件，再按需驱动真实编排。 */
async function onInvalidateCache(): Promise<void> {
  emit('invalidate-cache')
  if (!hasJobs.value) {
    return
  }
  const ok = await catalogApi.invalidateCache()
  saveHint.value = ok ? '语言包缓存已失效' : '语言包缓存失效未完成（将按短 TTL 兜底）'
  emit('cache-invalidated', { ok })
}

/** 新增 key：先上抛既有事件，再按需提示宿主接管弹窗。 */
function onAddKey(): void {
  emit('add-key')
}

/**
 * 删除 key（二次确认后上抛）。
 *
 * 说明：`08_01_02` 冻结契约为「点击即上抛 `remove-key`」，故仅在宿主注入编排通路（真实实现用法）时二次确认；
 * 纯事件用法（占位／宿主自理）直接上抛，由宿主自行确认。
 *
 * @param key 文案键。
 */
async function onRemoveKey(key: string): Promise<void> {
  emit('remove-key', key)
  if (!hasJobs.value) {
    return
  }
  catalogApi.removeKey(key)
}

/**
 * 单元格变更（透传为冻结载荷形状）。
 *
 * @param payload 单元格变更。
 */
function onCellChange(payload: { key: string; locale: string; value: string }): void {
  emit('change', { kind: 'message', value: payload })
  if (hasJobs.value) {
    catalogApi.editCell(payload)
  }
}

/** 新增语言：先上抛既有事件，再按需打开语言管理页签。 */
function onAddLocale(): void {
  emit('add-locale')
  innerTab.value = 'locales'
}

/**
 * 语言清单新增（来自件内弹窗）。
 *
 * @param input 语言输入。
 */
function onLocaleAdd(input: Parameters<typeof catalogApi.addLocale>[0]): void {
  if (!hasJobs.value) {
    return
  }
  const check = catalogApi.addLocale(input)
  if (!check.valid) {
    emit('failed', { message: check.message, code: check.code })
  }
}

/**
 * 语言清单修改（来自件内弹窗）。
 *
 * @param payload 修改载荷。
 */
function onLocaleUpdate(payload: { code: string; patch: Parameters<typeof catalogApi.updateLocale>[1] }): void {
  if (!hasJobs.value) {
    return
  }
  const check = catalogApi.updateLocale(payload.code, payload.patch)
  if (!check.valid) {
    emit('failed', { message: check.message, code: check.code })
  }
}

/**
 * 语言清单删除。
 *
 * @param code 语言标识。
 */
function onLocaleRemove(code: string): void {
  if (!hasJobs.value) {
    return
  }
  const check = catalogApi.removeLocale(code)
  if (!check.valid) {
    emit('failed', { message: check.message, code: check.code })
  }
}

/**
 * 语言启停（来自件内清单，载荷形状与内核一致）。
 *
 * @param payload 启停载荷。
 */
function onLocaleToggle(payload: { code: string; enabled: boolean }): void {
  const item = effectiveLocales.value.find((localeItem) => localeItem.code === payload.code)
  if (item !== undefined) {
    toggleLocale({ code: item.code, name: item.name, rtl: item.rtl, status: item.status })
  }
}

/**
 * 筛选变更（先上抛；有脏数据时二次确认后重取）。
 *
 * @param filter 新筛选条件。
 */
async function onFilterChange(filter: I18nFilter): Promise<void> {
  emit('filter-change', filter)
  if (isDirty.value) {
    const accepted = await confirm({ content: '存在未保存的文案变更，切换筛选将丢失这些修改，是否继续？', danger: true })
    if (!accepted) {
      return
    }
    catalogApi.resetDirty()
  }
  if (hasJobs.value) {
    catalogApi.setFilter(filter)
    await catalogApi.reload()
  }
}

/**
 * 页码变更。
 *
 * @param page 目标页码。
 */
async function onPageChange(page: number): Promise<void> {
  emit('page-change', page)
  if (hasJobs.value) {
    catalogApi.setPage(page)
  }
}

/** 导入（先上抛；注入时打开导入对话框）。 */
function onImport(): void {
  emit('import')
  if (hasJobs.value) {
    importVisible.value = true
  }
}

/** 导出（先上抛既有事件）。 */
function onExport(): void {
  emit('export')
}

/** 重试（复用同一内容派生幂等键）。 */
async function onRetry(): Promise<void> {
  emit('retry')
  if (!hasJobs.value) {
    return
  }
  const result = await catalogApi.retry()
  if (result === undefined) {
    saveHint.value = catalogApi.errorMessage.value
    emit('failed', { message: catalogApi.errorMessage.value, code: catalogApi.errorCode.value })
    return
  }
  saveHint.value = result.cacheInvalidated ? '保存成功，文案已即时生效' : '保存成功，但语言包缓存失效未完成（将按短 TTL 兜底）'
  emit('saved', result)
}

// 向后兼容新增：暴露编排内核实例（宿主与开发态核对页可驱动内部状态；既有对外形状不变）。
defineExpose({ catalog: catalogApi.catalog })
</script>

<template>
  <div
    class="bms-i18n-message-editor"
    :data-ready="catalogApi.ready.value"
    :data-degraded="catalogApi.degraded.value"
    :data-dirty="isDirty"
  >
    <slot v-if="catalogApi.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-i18n-message-editor__toolbar" data-test="toolbar">
          <span data-test="locale">{{ locale }}</span>
          <button type="button" data-test="add-key" :disabled="catalogApi.degraded.value" @click="onAddKey">
            新增 key
          </button>
          <button type="button" data-test="add-locale" :disabled="catalogApi.degraded.value" @click="onAddLocale">
            新增语言
          </button>
          <button type="button" data-test="save" :disabled="catalogApi.degraded.value" @click="onSave">保存</button>
          <button
            type="button"
            data-test="invalidate-cache"
            :disabled="catalogApi.degraded.value"
            @click="onInvalidateCache"
          >
            缓存失效
          </button>
          <button type="button" data-test="export" :disabled="catalogApi.degraded.value" @click="onExport">导出</button>
          <button type="button" data-test="import" :disabled="catalogApi.degraded.value" @click="onImport">导入</button>
          <button type="button" data-test="retry" :disabled="catalogApi.degraded.value" @click="onRetry">重试</button>
          <span v-if="isDirty" data-test="dirty">未保存</span>
          <span v-if="saveHint !== ''" data-test="save-hint">{{ saveHint }}</span>
          <span v-if="catalogApi.messagesRevision.value > 0" data-test="revision">
            语言包版本 {{ catalogApi.messagesRevision.value }}
          </span>
        </div>

        <div class="bms-i18n-message-editor__locales" data-test="locales">
          <span
            v-for="item in effectiveLocales"
            :key="item.code"
            :data-test="`locale-${item.code}`"
            :data-status="item.status"
          >
            {{ item.name }}
            <button type="button" :data-test="`toggle-${item.code}`" @click="toggleLocale(item)">启停</button>
          </span>
        </div>

        <div class="bms-i18n-message-editor__tabs" data-test="tabs">
          <button type="button" data-test="tab-locales" :data-active="innerTab === 'locales'" @click="switchTab('locales')">
            语言管理
          </button>
          <button
            type="button"
            data-test="tab-messages"
            :data-active="innerTab === 'messages'"
            @click="switchTab('messages')"
          >
            语言包维护
          </button>
        </div>

        <div v-if="innerTab === 'locales'" class="bms-i18n-message-editor__locale-panel">
          <slot name="locales">
            <LocaleList
              :locales="effectiveLocales"
              :default-locale="defaultLocale"
              :disabled="catalogApi.degraded.value"
              @add="onLocaleAdd"
              @update="onLocaleUpdate"
              @toggle="onLocaleToggle"
              @remove="onLocaleRemove"
            />
          </slot>
        </div>

        <div v-else class="bms-i18n-message-editor__grid" data-test="grid">
          <slot name="filter">
            <MessageFilter
              :model-value="effectiveFilter"
              :locales="effectiveLocales"
              :missing-codes="catalogApi.missingCodes.value"
              :disabled="catalogApi.degraded.value"
              @update:model-value="onFilterChange"
            />
          </slot>
          <slot name="grid">
            <component
              :is="MessageGrid"
              :locales="effectiveLocales"
              :messages="effectiveMessages"
              :active-locale="activeLocale"
              :page="catalogApi.page.value"
              :page-size="catalogApi.pageSize.value"
              :page-count="catalogApi.pageCount.value"
              :total="catalogApi.total.value"
              :virtualized="catalogApi.virtualized.value"
              :modified-keys="effectiveModifiedKeys"
              :show-disabled-locales="showDisabledLocales"
              @cell-change="onCellChange"
              @remove-key="onRemoveKey"
              @update:page="onPageChange"
            />
          </slot>
        </div>
      </slot>

      <ImportDialog
        v-if="hasJobs"
        v-model:visible="importVisible"
        data-test="import-dialog"
        :ready="catalogApi.ready.value"
        biz="i18n"
        biz-name="语言包"
        accept=".xlsx"
      >
        <template #error-report>
          <slot name="error-report" />
        </template>
      </ImportDialog>

      <ExportButton
        v-if="hasJobs"
        data-test="export-button"
        :ready="catalogApi.ready.value"
        biz="i18n"
        biz-name="语言包"
        scope="filtered"
        :params="exportParams"
      />
    </template>
  </div>
</template>
