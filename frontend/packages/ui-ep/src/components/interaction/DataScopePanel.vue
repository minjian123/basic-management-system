<script setup lang="ts">
// 数据权限件（08-4-4，新口径）：基础数据字典 → 数据选择 / 数据区域 / 数据匹配 / 扩展权限四子页签（结构化、只选不编）。
// 样式（11-01）：四子页签改 el-tabs、明细改 el-table 承载（与原型表格形态一致），补 <style scoped> 消费 --bms-* 令牌。
import {
  DATA_SCOPE_POLICIES,
  isValidMatchPattern,
  type BaseDictStore,
  type DataScopeEntry,
  type DataScopeExtensionMeta,
  type DataScopePolicyItem,
  type DataScopePolicyType,
  type DictSourceAdapter,
  type DataSourceKeyMeta,
} from '@bms/core'
import { ElButton, ElInput, ElOption, ElSelect, ElTabPane, ElTabs, ElTable, ElTableColumn } from 'element-plus'
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
  dataSourceKeys?: DataSourceKeyMeta[]
  /** 扩展权限登记清单。 */
  extensions?: DataScopeExtensionMeta[]
  /** 数据权限条目。 */
  entries?: DataScopeEntry[]
  /** 选中字典类型 id。 */
  selectedDataSourceKey?: string
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
  dataSourceKeys: () => [],
  extensions: () => [],
  entries: () => [],
  selectedDataSourceKey: '',
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
  'set-scope': [payload: { dataSourceKey: string; policyType: DataScopePolicyType; config: DataScopePolicyItem[] }]
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
const dictCode = computed(() => props.dataSourceKeys.find((dict) => dict.id === props.selectedDataSourceKey)?.code ?? '')

/** 当前字典 × 策略的条目。 */
function entryOf(policy: DataScopePolicyType): DataScopeEntry | undefined {
  return props.entries.find((entry) => entry.dataSourceKey === props.selectedDataSourceKey && entry.policyType === policy)
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

watch(() => [props.selectedDataSourceKey, props.entries], sync, { immediate: true, deep: true })

/** 提交数据选择。 */
function submitSelect(values: string | string[]): void {
  const list = Array.isArray(values) ? values : [values]
  emit('set-scope', {
    dataSourceKey: props.selectedDataSourceKey,
    policyType: 'select',
    config: list.filter((value) => value !== '').map((itemCode) => ({ itemCode })),
  })
}

/** 提交区域 / 匹配 / 扩展草稿。 */
function submit(policy: DataScopePolicyType): void {
  if (policy === 'region') {
    emit('set-scope', {
      dataSourceKey: props.selectedDataSourceKey,
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
      dataSourceKey: props.selectedDataSourceKey,
      policyType: 'match',
      config: matchRows.value.filter((row) => row.pattern !== '').map((row) => ({ ...row })),
    })
    return
  }
  emit('set-scope', {
    dataSourceKey: props.selectedDataSourceKey,
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

/** 策略中文名。 */
const POLICY_LABELS: Readonly<Record<string, string>> = {
  select: '数据选择',
  region: '数据区域',
  match: '数据匹配',
  extension: '扩展权限',
}

/** 匹配值是否非法（用于即时标记）。 */
function matchInvalid(pattern: string): boolean {
  return pattern !== '' && !isValidMatchPattern(pattern)
}

/** 子页签切换。 */
function onPolicyChange(name: string | number): void {
  emit('update:policy', name as DataScopePolicyType)
}

/** 区域值变更。 */
function onRegionChange(row: RegionRow, side: 'start' | 'end', value: string | string[]): void {
  row[side] = Array.isArray(value) ? value[0] ?? '' : value
  submit('region')
}

/** 匹配字段变更。 */
function onMatchFieldChange(row: MatchRow, value: string): void {
  row.field = value
  submit('match')
}

/** 扩展键变更。 */
function onExtensionKeyChange(row: ExtensionRow, value: string): void {
  row.key = value
  submit('extension')
}
</script>

<template>
  <div class="bms-data-scope" data-test="data-scope" :data-disabled="disabled || undefined">
    <div class="bms-data-scope__dicts">
      <ul class="bms-data-scope__dict-list">
        <li
          v-for="dict in dataSourceKeys"
          :key="dict.id"
          class="bms-data-scope__dict"
          :data-test="`dict-${dict.id}`"
          :data-active="selectedDataSourceKey === dict.id || undefined"
          @click="!disabled && emit('select-dict', dict.id)"
        >
          {{ dict.name }}
        </li>
      </ul>
    </div>

    <div class="bms-data-scope__detail">
      <el-tabs :model-value="policy" class="bms-data-scope__tabs" @tab-change="onPolicyChange">
        <el-tab-pane
          v-for="policyItem in availablePolicies"
          :key="policyItem"
          :name="policyItem"
          :label="POLICY_LABELS[policyItem] ?? policyItem"
        >
          <template #label>
            <span :data-test="`policy-${policyItem}`">{{ POLICY_LABELS[policyItem] ?? policyItem }}</span>
          </template>

          <p v-if="selectedDataSourceKey === ''" class="bms-data-scope__empty" data-test="empty">{{ emptyText }}</p>

          <template v-else>
            <dynamic-dict-picker
              v-if="policyItem === 'select'"
              :dict-type="dictCode"
              :ready="ready"
              :source="source"
              :store="store"
              :multiple="true"
              :model-value="selectValue"
              :disabled="disabled"
              @update:model-value="submitSelect"
            />

            <div v-else-if="policyItem === 'region'" class="bms-data-scope__policy" data-test="region">
              <el-table :data="regionRows" size="small" border>
                <el-table-column label="开始值" min-width="180">
                  <template #default="{ row, $index }">
                    <div :data-test="`region-row-${$index}`">
                      <dynamic-dict-picker
                        :dict-type="dictCode"
                        :ready="ready"
                        :source="source"
                        :store="store"
                        :model-value="row.start"
                        :disabled="disabled"
                        @update:model-value="(value) => onRegionChange(row as RegionRow, 'start', value)"
                      />
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="结束值" min-width="180">
                  <template #default="{ row }">
                    <dynamic-dict-picker
                      :dict-type="dictCode"
                      :ready="ready"
                      :source="source"
                      :store="store"
                      :model-value="row.end"
                      :disabled="disabled"
                      @update:model-value="(value) => onRegionChange(row as RegionRow, 'end', value)"
                    />
                  </template>
                </el-table-column>
              </el-table>
              <el-button
                class="bms-data-scope__add"
                data-test="region-add"
                size="small"
                :disabled="disabled"
                @click="regionRows.push({ start: '', end: '' })"
              >
                新增区域
              </el-button>
            </div>

            <div v-else-if="policyItem === 'match'" class="bms-data-scope__policy" data-test="match">
              <el-table :data="matchRows" size="small" border>
                <el-table-column label="字段" width="140">
                  <template #default="{ row, $index }">
                    <div :data-test="`match-row-${$index}`">
                      <el-select
                        data-test="match-field"
                        :model-value="row.field"
                        size="small"
                        :disabled="disabled"
                        @update:model-value="(value: string) => onMatchFieldChange(row as MatchRow, value)"
                      >
                        <el-option v-for="field in matchFields" :key="field" :label="field" :value="field" />
                      </el-select>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="匹配值（通配符）" min-width="200">
                  <template #default="{ row }">
                    <el-input
                      v-model="row.pattern"
                      data-test="match-pattern"
                      size="small"
                      placeholder="通配符值"
                      :disabled="disabled"
                      @change="submit('match')"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="校验" width="120">
                  <template #default="{ row }">
                    <span v-if="matchInvalid(row.pattern)" class="bms-data-scope__invalid" data-test="match-invalid">
                      格式非法
                    </span>
                    <span v-else class="bms-data-scope__hint">—</span>
                  </template>
                </el-table-column>
              </el-table>
              <el-button
                class="bms-data-scope__add"
                data-test="match-add"
                size="small"
                :disabled="disabled"
                @click="matchRows.push({ field: matchFields[0] ?? 'code', pattern: '' })"
              >
                新增匹配
              </el-button>
            </div>

            <div v-else class="bms-data-scope__policy" data-test="extension">
              <el-table :data="extensionRows" size="small" border>
                <el-table-column label="扩展权限" min-width="200">
                  <template #default="{ row, $index }">
                    <div :data-test="`extension-row-${$index}`">
                      <el-select
                        data-test="extension-key"
                        :model-value="row.key"
                        size="small"
                        placeholder="请选择扩展权限"
                        :disabled="disabled"
                        @update:model-value="(value: string) => onExtensionKeyChange(row as ExtensionRow, value)"
                      >
                        <el-option
                          v-for="extension in extensions"
                          :key="extension.key"
                          :label="extension.name"
                          :value="extension.key"
                        />
                      </el-select>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="参数" min-width="200">
                  <template #default="{ row }">
                    <span
                      v-if="extensions.find((item) => item.key === row.key)?.hasParams === false"
                      class="bms-data-scope__hint"
                      data-test="extension-no-params"
                    >
                      该扩展权限不需要设置参数
                    </span>
                    <span v-else class="bms-data-scope__hint">由扩展功能自带界面填写</span>
                  </template>
                </el-table-column>
              </el-table>
              <el-button
                class="bms-data-scope__add"
                data-test="extension-add"
                size="small"
                :disabled="disabled"
                @click="extensionRows.push({ key: '', paramsText: '' })"
              >
                新增扩展
              </el-button>
            </div>
          </template>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
.bms-data-scope {
  display: flex;
  gap: var(--bms-space-4);
  min-width: 0;
}

.bms-data-scope__dicts {
  display: flex;
  flex: none;
  flex-direction: column;
  width: 280px;
  min-height: 0;
  max-height: 100%;
  padding: var(--bms-space-3);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-data-scope__dict-list {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: auto;
  list-style: none;
}

.bms-data-scope__dict {
  display: flex;
  align-items: center;
  padding: var(--bms-space-2) var(--bms-space-3);
  border-bottom: 1px solid var(--bms-color-border);
  font-size: var(--bms-font-size-sm);
  cursor: pointer;
}

.bms-data-scope__dict:hover {
  background: var(--bms-color-fill);
}

.bms-data-scope__dict[data-active] {
  background: var(--bms-color-primary-light);
  box-shadow: inset 2px 0 0 var(--bms-color-primary);
}

.bms-data-scope__detail {
  flex: 1;
  min-width: 0;
}

.bms-data-scope__tabs :deep(.el-tabs__header) {
  margin-bottom: var(--bms-space-3);
}

.bms-data-scope__policy {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  align-items: flex-start;
}

.bms-data-scope__add {
  align-self: flex-start;
}

.bms-data-scope__empty {
  margin: 0;
  padding: var(--bms-space-6) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}

.bms-data-scope__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-data-scope__invalid {
  color: var(--bms-perm-invalid-color);
  font-size: var(--bms-font-size-xs);
}

@media (max-width: 992px) {
  .bms-data-scope {
    flex-direction: column;
  }

  .bms-data-scope__dicts {
    width: 100%;
    max-height: 200px;
  }
}
</style>
