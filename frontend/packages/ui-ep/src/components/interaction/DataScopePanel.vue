<script setup lang="ts">
// 数据权限件（08-4-4，新口径）：基础数据字典 → 数据选择 / 数据区域 / 数据匹配 / 扩展权限四子页签（结构化、只选不编）。
import {
  DATA_SCOPE_POLICIES,
  isValidMatchPattern,
  type BaseDictStore,
  type DataScopeEntry,
  type DataScopeExtensionMeta,
  type DataScopePolicyItem,
  type DataScopePolicyType,
  type DictSourceAdapter,
  type DictTypeMeta,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'
import DynamicDictPicker from './DynamicDictPicker.vue'

/** 数据区域草稿行。 */
interface RegionRow {
  /** 开始值。 */
  start: string
  /** 结束值。 */
  end: string
}

/** 数据匹配草稿行。 */
interface MatchRow {
  /** 匹配字段。 */
  field: string
  /** 通配符值。 */
  pattern: string
}

/** 扩展权限草稿行。 */
interface ExtensionRow {
  /** 扩展键。 */
  key: string
  /** 参数 JSON 文本。 */
  paramsText: string
}

interface Props {
  /** 基础数据字典清单。 */
  dictTypes?: DictTypeMeta[]
  /** 扩展权限登记清单。 */
  extensions?: DataScopeExtensionMeta[]
  /** 数据权限条目。 */
  entries?: DataScopeEntry[]
  /** 选中字典类型 id。 */
  selectedDictTypeId?: string
  /** 当前策略子页签。 */
  policy?: DataScopePolicyType
  /** 匹配字段白名单。 */
  matchFields?: string[]
  /** 字典数据源（透传动态字典件）。 */
  source?: DictSourceAdapter
  /** 字典缓存能力。 */
  store?: BaseDictStore
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 是否禁用。 */
  disabled?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  dictTypes: () => [],
  extensions: () => [],
  entries: () => [],
  selectedDictTypeId: '',
  policy: 'select',
  matchFields: () => ['code', 'name', 'remark'],
  source: undefined,
  store: undefined,
  ready: false,
  disabled: false,
  emptyText: '暂无数据权限字典',
})

const emit = defineEmits<{
  'select-dict': [id: string]
  'update:policy': [policy: DataScopePolicyType]
  'set-scope': [payload: { dictTypeId: string; policyType: DataScopePolicyType; config: DataScopePolicyItem[] }]
  validate: [payload: { policyType: DataScopePolicyType; message: string }]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
useBasePermissionConfig()

/** 数据选择草稿（字典数据项码）。 */
const selectValue = ref<string[]>([])
/** 数据区域草稿。 */
const regionRows = ref<RegionRow[]>([])
/** 数据匹配草稿。 */
const matchRows = ref<MatchRow[]>([])
/** 扩展权限草稿。 */
const extensionRows = ref<ExtensionRow[]>([])

/** 选中字典类型码（透传动态字典件）。 */
const dictCode = computed(() => props.dictTypes.find((dict) => dict.id === props.selectedDictTypeId)?.code ?? '')

/** 当前字典 × 策略的条目。 */
function entryOf(policy: DataScopePolicyType): DataScopeEntry | undefined {
  return props.entries.find((entry) => entry.dictTypeId === props.selectedDictTypeId && entry.policyType === policy)
}

/** 从条目同步各策略草稿。 */
function sync(): void {
  const select = entryOf('select')
  selectValue.value = (select?.config ?? []).map((item) => (item as { itemCode: string }).itemCode)
  const region = entryOf('region')
  regionRows.value = (region?.config ?? []).map((item) => {
    const row = item as { start: string; end: string }
    return { start: row.start, end: row.end }
  })
  const match = entryOf('match')
  matchRows.value = (match?.config ?? []).map((item) => {
    const row = item as { field: string; pattern: string }
    return { field: row.field, pattern: row.pattern }
  })
  const extension = entryOf('extension')
  extensionRows.value = (extension?.config ?? []).map((item) => {
    const row = item as { key: string; params?: Record<string, unknown> }
    return { key: row.key, paramsText: row.params === undefined ? '' : JSON.stringify(row.params) }
  })
}

watch(() => [props.selectedDictTypeId, props.entries], sync, { immediate: true, deep: true })

/** 提交数据选择。 */
function submitSelect(values: string | string[]): void {
  const list = Array.isArray(values) ? values : [values]
  emit('set-scope', {
    dictTypeId: props.selectedDictTypeId,
    policyType: 'select',
    config: list.filter((value) => value !== '').map((itemCode) => ({ itemCode })),
  })
}

/** 提交区域 / 匹配 / 扩展草稿。 */
function submit(policy: DataScopePolicyType): void {
  if (policy === 'region') {
    emit('set-scope', {
      dictTypeId: props.selectedDictTypeId,
      policyType: 'region',
      config: regionRows.value.filter((row) => row.start !== '' || row.end !== '').map((row) => ({ ...row })),
    })
    return
  }
  if (policy === 'match') {
    for (const row of matchRows.value) {
      if (row.pattern !== '' && !isValidMatchPattern(row.pattern)) {
        emit('validate', { policyType: 'match', message: '匹配值仅允许 * ? 与中英文 / 数字 / 下划线' })
        return
      }
    }
    emit('set-scope', {
      dictTypeId: props.selectedDictTypeId,
      policyType: 'match',
      config: matchRows.value.filter((row) => row.pattern !== '').map((row) => ({ ...row })),
    })
    return
  }
  emit('set-scope', {
    dictTypeId: props.selectedDictTypeId,
    policyType: 'extension',
    config: extensionRows.value
      .filter((row) => row.key !== '')
      .map((row) => ({ key: row.key, params: row.paramsText === '' ? undefined : { raw: row.paramsText } })),
  })
}

/** 扩展权限是否有注册（未注册不显示该子页签）。 */
const extensionEnabled = computed(() => props.extensions.length > 0)

/** 可见策略子页签（扩展未注册即隐藏）。 */
const availablePolicies = computed(() =>
  DATA_SCOPE_POLICIES.filter((item) => item !== 'extension' || extensionEnabled.value),
)
</script>

<template>
  <div class="bms-data-scope" data-test="data-scope" :data-disabled="disabled || undefined">
    <div class="bms-data-scope__dicts">
      <button
        v-for="dict in dictTypes"
        :key="dict.id"
        type="button"
        :data-test="`dict-${dict.id}`"
        :data-active="selectedDictTypeId === dict.id || undefined"
        @click="emit('select-dict', dict.id)"
      >
        {{ dict.name }}
      </button>
    </div>

    <div class="bms-data-scope__detail">
      <div class="bms-data-scope__tabs">
        <button
          v-for="policyItem in availablePolicies"
          :key="policyItem"
          type="button"
          :data-test="`policy-${policyItem}`"
          :data-active="policy === policyItem || undefined"
          @click="emit('update:policy', policyItem)"
        >
          {{ policyItem }}
        </button>
      </div>

      <p v-if="selectedDictTypeId === ''" data-test="empty">{{ emptyText }}</p>

      <template v-else>
        <dynamic-dict-picker
          v-if="policy === 'select'"
          :dict-type="dictCode"
          :ready="ready"
          :source="source"
          :store="store"
          :multiple="true"
          :model-value="selectValue"
          :disabled="disabled"
          @update:model-value="submitSelect"
        />

        <div v-else-if="policy === 'region'" data-test="region">
          <div v-for="(row, index) in regionRows" :key="index" :data-test="`region-row-${index}`">
            <dynamic-dict-picker
              :dict-type="dictCode"
              :ready="ready"
              :source="source"
              :store="store"
              :model-value="row.start"
              :disabled="disabled"
              @update:model-value="(value) => { row.start = Array.isArray(value) ? value[0] ?? '' : value; submit('region') }"
            />
            <span>~</span>
            <dynamic-dict-picker
              :dict-type="dictCode"
              :ready="ready"
              :source="source"
              :store="store"
              :model-value="row.end"
              :disabled="disabled"
              @update:model-value="(value) => { row.end = Array.isArray(value) ? value[0] ?? '' : value; submit('region') }"
            />
          </div>
          <button type="button" data-test="region-add" :disabled="disabled" @click="regionRows.push({ start: '', end: '' })">
            新增区域
          </button>
        </div>

        <div v-else-if="policy === 'match'" data-test="match">
          <div v-for="(row, index) in matchRows" :key="index" :data-test="`match-row-${index}`">
            <select v-model="row.field" :disabled="disabled" data-test="match-field">
              <option v-for="field in matchFields" :key="field" :value="field">{{ field }}</option>
            </select>
            <input
              v-model="row.pattern"
              type="text"
              data-test="match-pattern"
              placeholder="通配符值"
              :disabled="disabled"
              @change="submit('match')"
            />
          </div>
          <button type="button" data-test="match-add" :disabled="disabled" @click="matchRows.push({ field: matchFields[0] ?? 'code', pattern: '' })">
            新增匹配
          </button>
        </div>

        <div v-else data-test="extension">
          <div v-for="(row, index) in extensionRows" :key="index" :data-test="`extension-row-${index}`">
            <select v-model="row.key" :disabled="disabled" data-test="extension-key" @change="submit('extension')">
              <option value="">请选择扩展权限</option>
              <option v-for="extension in extensions" :key="extension.key" :value="extension.key">
                {{ extension.name }}
              </option>
            </select>
            <span v-if="extensions.find((item) => item.key === row.key)?.hasParams === false" data-test="extension-no-params">
              该扩展权限不需要设置参数
            </span>
          </div>
          <button type="button" data-test="extension-add" :disabled="disabled" @click="extensionRows.push({ key: '', paramsText: '' })">
            新增扩展
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
