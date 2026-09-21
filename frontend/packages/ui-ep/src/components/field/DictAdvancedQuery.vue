<script setup lang="ts">
// 字典高级查询抽屉（06_06）：目标切换（取项 / 筛选）+ 提供者与参数 + 条件组构建 + 结果预览 + 查询方案管理；
// 打开快照条件、应用才回填 / 上抛，取消恢复快照。
import {
  DICT_EMPTY_TEXT,
  DICT_PLACEHOLDER_TEXT,
  DICT_QUERY_PAGE_SIZE,
  type DictConditionGroup,
  type DictSourceAdapter,
} from '@bms/core'
import { ElButton, ElDrawer, ElInput, ElOption, ElSelect } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseDictQuery } from '../../composables/useBaseDictQuery'
import ConditionGroupBuilder from './ConditionGroupBuilder.vue'

interface Props {
  /** 可见（受控）。 */
  visible?: boolean
  /** 字典类型码。 */
  dictType?: string
  /** 目标（缺省取项）。 */
  target?: 'items' | 'business'
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 字典数据源（未注入即占位零请求）。 */
  source?: DictSourceAdapter
  /** 标题（缺省按目标派生）。 */
  title?: string
  /** 页长（缺省 20）。 */
  pageSize?: number
  /** 降级文案。 */
  degradeText?: string
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  dictType: '',
  target: 'items',
  ready: false,
  source: undefined,
  title: '',
  pageSize: DICT_QUERY_PAGE_SIZE,
  degradeText: DICT_PLACEHOLDER_TEXT,
  emptyText: DICT_EMPTY_TEXT,
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  apply: [payload: { target: 'items' | 'business'; values?: string[]; filter?: Record<string, unknown> }]
  cancel: []
  retry: []
}>()

const api = useBaseDictQuery({
  ready: props.ready,
  dictType: props.dictType,
  target: props.target,
  source: props.source,
  pageSize: props.pageSize,
})

/** 打开时快照（取消恢复）。 */
const snapshot = ref<{ conditions: DictConditionGroup; providerKey: string; params: Record<string, unknown> } | null>(null)

/** 方案名输入。 */
const schemeName = ref('我的查询方案')

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.dictType,
  (next) => api.setDictType(next),
)
watch(
  () => props.target,
  (next) => api.setTarget(next),
)
watch(
  () => props.source,
  (next) => api.setSource(next),
)
watch(
  () => props.visible,
  async (next) => {
    if (!next) {
      return
    }
    snapshot.value = {
      conditions: JSON.parse(JSON.stringify(api.conditions.value)) as DictConditionGroup,
      providerKey: api.providerKey.value,
      params: { ...api.providerParams.value },
    }
    await api.loadMeta()
    await api.loadSchemes()
    await api.run()
  },
  { immediate: true },
)

const drawerTitle = computed(() => {
  if (props.title !== '') {
    return props.title
  }
  return props.target === 'items' ? '字典高级查询（取项）' : '字典高级查询（筛选）'
})

/** 结果行（取项 / 业务筛选）。 */
const rows = computed<{ key: string; cells: string[] }[]>(() => {
  if (api.target.value === 'items') {
    return api.results.value.map((item) => ({
      key: item.value,
      cells: [item.value, item.label, item.code, item.status],
    }))
  }
  return api.rows.value.map((row, index) => ({
    key: String(index),
    cells: Object.values(row).map((cell) => String(cell)),
  }))
})

/** 结果表头。 */
const headers = computed<string[]>(() => (api.target.value === 'items' ? ['值', '标签', '编码', '状态'] : ['字段']))

/**
 * 目标切换（清空条件与结果）。
 *
 * @param next 目标。
 */
function onTargetChange(next: 'items' | 'business'): void {
  api.setTarget(next)
  void api.run()
}

/**
 * 执行查询。
 */
function onRun(): void {
  void api.run()
}

/** 重置条件 / 提供者 / 结果。 */
function onReset(): void {
  api.reset()
}

/**
 * 应用方案。
 *
 * @param schemeId 方案 ID。
 */
function onApplyScheme(schemeId: number): void {
  const scheme = api.schemes.value.find((entry) => entry.id === schemeId)
  if (scheme !== undefined) {
    api.applyScheme(scheme)
    void api.run()
  }
}

/**
 * 保存方案（方案名取输入框）。
 */
function onSaveScheme(): void {
  const name = schemeName.value.trim()
  if (name !== '') {
    void api.saveScheme(name)
  }
}

/**
 * 翻页（页码夹取后执行）。
 *
 * @param delta 页码增量。
 */
function onPageChange(delta: number): void {
  api.setPage(api.page.value + delta)
  void api.run()
}

/**
 * 删除方案。
 *
 * @param schemeId 方案 ID。
 */
function onDeleteScheme(schemeId: number): void {
  void api.deleteScheme(schemeId)
}

/** 取消（恢复快照并关闭）。 */
function onCancel(): void {
  if (snapshot.value !== null) {
    api.setConditions(snapshot.value.conditions)
    api.setProvider(snapshot.value.providerKey, snapshot.value.params)
  }
  emit('cancel')
  emit('update:visible', false)
}

/** 应用（取项 → 选中值；筛选 → 业务参数）。 */
function onApply(): void {
  if (api.target.value === 'items') {
    emit('apply', { target: 'items', values: api.selectedValues() })
  } else {
    emit('apply', { target: 'business', filter: api.toBusinessFilter() })
  }
  emit('update:visible', false)
}

/** 重试（重载元数据与结果）。 */
function onRetry(): void {
  void api.loadMeta()
  void api.run()
  emit('retry')
}
</script>

<template>
  <el-drawer
    :model-value="visible"
    :title="drawerTitle"
    size="720px"
    data-test="dict-advanced-query"
    @update:model-value="emit('update:visible', $event)"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <div v-else class="bms-dict-adv">
      <div class="bms-dict-adv__bar">
        <el-select
          :model-value="api.target.value"
          size="small"
          style="width: 160px"
          @update:model-value="onTargetChange($event)"
        >
          <el-option label="取项（字典条目）" value="items" />
          <el-option label="筛选（业务条件）" value="business" />
        </el-select>
        <el-select
          :model-value="api.providerKey.value"
          :placeholder="api.providers.value.length === 0 ? '无可用提供者' : '选择查询提供者（可选）'"
          size="small"
          clearable
          style="width: 260px"
          data-test="dict-adv-provider"
          @update:model-value="api.setProvider($event ?? '', api.providerParams.value)"
        >
          <el-option
            v-for="provider in api.providers.value"
            :key="provider.key"
            :label="provider.name"
            :value="provider.key"
          />
        </el-select>
        <el-input
          v-if="api.target.value === 'business'"
          :model-value="String(api.providerParams.value.keyword ?? '')"
          size="small"
          placeholder="关键词（提供者参数）"
          style="width: 220px"
          @update:model-value="api.setProvider(api.providerKey.value, { ...api.providerParams.value, keyword: $event })"
        />
      </div>

      <div class="bms-dict-adv__conditions" data-test="dict-adv-condition-group">
        <condition-group-builder
          :model-value="api.conditions.value"
          :fields="api.fieldOptions.value"
          @update:model-value="api.setConditions($event)"
        />
      </div>

      <div class="bms-dict-adv__actions">
        <el-button size="small" @click="onReset">重置</el-button>
        <el-button size="small" type="primary" data-test="dict-adv-run" @click="onRun">执行查询</el-button>
      </div>

      <p v-if="api.errorText.value !== ''" class="bms-field-error" data-test="dict-adv-error">{{ api.errorText.value }}</p>

      <div class="bms-dict-adv__result" data-test="dict-adv-result">
        <table class="bms-dict-adv__table">
          <thead>
            <tr>
              <th v-for="header in headers" :key="header">{{ header }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key" :data-test="`dict-adv-result-row-${row.key}`">
              <td v-for="(cell, index) in row.cells" :key="index">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="rows.length === 0" class="bms-dict-adv__empty" data-test="dict-adv-empty">{{ emptyText }}</div>
        <div class="bms-dict-adv__pager">
          <span>共 {{ api.total.value }} 条</span>
          <el-button size="small" :disabled="api.page.value <= 1" @click="onPageChange(-1)">上一页</el-button>
          <el-button
            size="small"
            :disabled="api.page.value * api.pageSize.value >= api.total.value"
            @click="onPageChange(1)"
          >
            下一页
          </el-button>
        </div>
      </div>

      <div class="bms-dict-adv__schemes" data-test="dict-adv-scheme">
        <el-select
          :model-value="undefined"
          placeholder="查询方案"
          size="small"
          style="width: 200px"
          @update:model-value="onApplyScheme($event)"
        >
          <el-option v-for="scheme in api.schemes.value" :key="scheme.id" :label="scheme.name" :value="scheme.id ?? 0" />
        </el-select>
        <el-input v-model="schemeName" size="small" style="width: 160px" placeholder="方案名" />
        <el-button size="small" data-test="dict-adv-scheme-save" @click="onSaveScheme">保存方案</el-button>
        <el-button
          size="small"
          :disabled="api.schemes.value.length === 0"
          data-test="dict-adv-scheme-delete"
          @click="onDeleteScheme(api.schemes.value[0]?.id ?? 0)"
        >
          删除首个方案
        </el-button>
      </div>

      <div class="bms-dict-adv__footer">
        <el-button size="small" data-test="dict-adv-cancel" @click="onCancel">取消</el-button>
        <el-button size="small" type="primary" data-test="dict-adv-confirm" @click="onApply">应用</el-button>
        <el-button v-if="api.error.value" size="small" data-test="dict-adv-retry" @click="onRetry">重试</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.bms-dict-adv {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
}
.bms-dict-adv__bar {
  display: flex;
  gap: var(--bms-spacing-md);
  align-items: center;
}
.bms-dict-adv__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--bms-spacing-md);
}
.bms-dict-adv__table {
  width: 100%;
  border-collapse: collapse;
}
.bms-dict-adv__table th,
.bms-dict-adv__table td {
  padding: var(--bms-spacing-sm) var(--bms-spacing-md);
  border-bottom: 1px solid var(--bms-dict-border);
  text-align: left;
}
.bms-dict-adv__empty {
  padding: var(--bms-spacing-lg);
  color: var(--bms-color-text-secondary);
  text-align: center;
}
.bms-dict-adv__pager,
.bms-dict-adv__schemes,
.bms-dict-adv__footer {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
}
.bms-dict-adv__footer {
  justify-content: flex-end;
}
</style>
