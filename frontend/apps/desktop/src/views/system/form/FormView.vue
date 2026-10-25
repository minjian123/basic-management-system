<script setup lang="ts">
// 表单管理页：表单实体总列表（含未挂接任何菜单入口的表单）。
// 对照原型《10_菜单管理/12_表单管理.html》：三段式、无操作列、双击行开记录 Tab、关联菜单数 0 标注「无入口」。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui_ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { deleteForm, updateForm, type FormItem, type MetaStatus } from '@/api/menuMeta'
import { recordTabKey, useTabsStore } from '@/stores/tabs'
import { useMenuMetaStore } from '@/stores/menuMeta'

import FormRecordTab from './FormRecordTab.vue'

defineOptions({ name: 'SystemForm' })

/** 列表页签键（固定不可关）。 */
const LIST_KEY = 'list'
/** 每页条数（表单非树形元数据，按原型 20 条/页）。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()
const meta = useMenuMetaStore()
const router = useRouter()

/** 全量表单。 */
const rows = ref<FormItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 列表多选。 */
const selection = ref<FormItem[]>([])
/** 关键字输入（视图组件）。 */
const keyword = ref('')
/** 业务码输入。 */
const businessInput = ref('')
/** 状态输入。 */
const statusInput = ref<'' | MetaStatus>('')
/** 已应用筛选。 */
const applied = ref<{ keyword: string; businessId: string; status: '' | MetaStatus }>({
  keyword: '',
  businessId: '',
  status: '',
})
/** 当前页。 */
const page = ref(1)

/** 表单框架页签（映射 store 状态）。 */
const frameTabs = computed<FormFrameTab[]>(() =>
  tabs.tabs.map((tab) => ({
    key: tab.key,
    title: tab.title,
    type: tab.type,
    closable: tab.closable,
    dirty: tab.dirty,
  })),
)
/** 当前激活页签键。 */
const activeKey = computed(() => tabs.active)
/** 业务码名称映射。 */
const businessNames = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of meta.businesses) {
    map[item.id] = item.name
  }
  return map
})
/** 业务码选项（筛选用）。 */
const businessOptions = computed(() =>
  meta.businesses.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
)
/** 过滤后的行。 */
const filteredRows = computed(() => {
  const needle = applied.value.keyword.trim().toLowerCase()
  return rows.value.filter((row) => {
    const component = (row.component ?? '').toLowerCase()
    return (
      (needle === '' || component.includes(needle)) &&
      (applied.value.businessId === '' || row.business_id === applied.value.businessId) &&
      (applied.value.status === '' || row.status === applied.value.status)
    )
  })
})
/** 当前页行。 */
const pageRows = computed(() => filteredRows.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

/**
 * 表单显示名。
 *
 * @param row 表单行。
 * @returns 显示名。
 */
function formLabel(row: FormItem): string {
  return row.component !== null && row.component !== '' ? row.component : `表单 ${row.id}`
}

/**
 * 载入表单清单与业务码。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([meta.ensureForms(true), meta.ensureBusinesses()])
    rows.value = meta.forms
    selection.value = []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '表单列表加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 应用筛选（回第一页）。
 */
function search(): void {
  applied.value = {
    keyword: keyword.value,
    businessId: businessInput.value,
    status: statusInput.value,
  }
  page.value = 1
}

/**
 * 重置筛选。
 */
function resetFilter(): void {
  keyword.value = ''
  businessInput.value = ''
  statusInput.value = ''
  applied.value = { keyword: '', businessId: '', status: '' }
  page.value = 1
}

/**
 * 打开记录页签。
 *
 * @param row 表单行。
 */
function openRecord(row: FormItem): void {
  tabs.open(recordTabKey(row.id), formLabel(row))
}

/**
 * 新增表单（记录页签新增态）。
 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增表单')
}

/**
 * 关闭页面（列表页签固定不可关，返回工作台）。
 */
function closePage(): void {
  void router.push('/')
}

/**
 * 关闭页签（脏数据拦截）。
 *
 * @param key 页签键。
 * @returns 是否允许关闭。
 */
async function closeTab(key: string): Promise<boolean> {
  const tab = tabs.tabOf(key)
  if (tab === undefined) {
    return false
  }
  if (!tab.dirty) {
    return tabs.close(key)
  }
  try {
    await ElMessageBox.confirm('该记录存在未保存变更，关闭将丢弃这些变更？', '关闭确认', { type: 'warning' })
  } catch {
    return false
  }
  return tabs.discard(key)
}

/**
 * 表单更新载荷（菜单入口全量替换）。
 *
 * @param row 表单行。
 * @param overrides 覆盖字段。
 * @returns 更新载荷。
 */
function payloadOf(row: FormItem, overrides: { status?: MetaStatus } = {}) {
  return {
    menu_ids: (row.menu_ids ?? []).map(String),
    business_id: row.business_id,
    component: row.component ?? null,
    status: overrides.status ?? (row.status === 'disabled' ? 'disabled' : 'enabled'),
  }
}

/**
 * 批量删除（逐行执行并汇总；被引用 `40206` 逐条提示）。
 */
async function removeSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个表单？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deleteForm(row.id)
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${formLabel(row)}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个表单`)
    await load()
  }
}

/**
 * 批量停用 / 启用（逐行反转状态并汇总）。
 */
async function toggleSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  let changed = 0
  for (const row of selection.value) {
    const next: MetaStatus = row.status === 'enabled' ? 'disabled' : 'enabled'
    try {
      await updateForm(row.id, payloadOf(row, { status: next }))
      changed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `状态更新失败：${formLabel(row)}`)
    }
  }
  if (changed > 0) {
    ElMessage.success(`已更新 ${changed} 个表单的状态`)
    await load()
  }
}

/**
 * 记录保存成功：新增态换为实体页签，编辑态同步标题并刷新列表。
 *
 * @param form 保存后的表单。
 */
function onSaved(form: FormItem): void {
  const key = recordTabKey(form.id)
  const title = formLabel(form)
  if (tabs.active === recordTabKey('new')) {
    tabs.discard(recordTabKey('new'))
    tabs.open(key, title)
  } else {
    const tab = tabs.tabOf(key)
    if (tab !== undefined) {
      tab.title = title
      tabs.activate(key)
    }
  }
  void load()
}

/**
 * 记录删除成功：关闭当前记录页签并刷新列表。
 */
function onRemoved(): void {
  tabs.discard(tabs.active)
  void load()
}

/**
 * 记录脏态同步。
 *
 * @param key 页签键。
 * @param dirty 是否脏。
 */
function onRecordDirty(key: string, dirty: boolean): void {
  tabs.setDirty(key, dirty)
}

onMounted(() => {
  tabs.reset(LIST_KEY, '表单管理')
  void load()
})
</script>

<template>
  <page-container title="表单管理" description="表单实体总列表（含未挂接表单）：1:1 挂业务码，与菜单多对多">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="form-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="form-view__toolbar">
          <el-button type="primary" data-test="form-create" @click="openCreate">新增</el-button>
          <el-button data-test="form-refresh" @click="load">刷新</el-button>
          <el-button data-test="form-close-page" @click="closePage">关闭</el-button>
          <el-button type="danger" plain :disabled="selection.length === 0" data-test="form-batch-delete" @click="removeSelected">
            删除
          </el-button>
          <el-button :disabled="selection.length === 0" data-test="form-batch-toggle" @click="toggleSelected">
            停用/启用
          </el-button>
          <span class="form-view__side">
            <el-button disabled title="导出能力本期未立项（置灰占位）" data-test="form-export">导出</el-button>
            <span class="form-view__hint">平台超管维护 · 含未挂接表单</span>
          </span>
        </div>

        <div class="form-view__filter">
          <el-input
            v-model="keyword"
            class="form-view__kw"
            placeholder="关键字：视图组件"
            clearable
            data-test="form-kw"
            @keyup.enter="search"
          />
          <el-select v-model="businessInput" class="form-view__select" placeholder="业务码" clearable filterable data-test="form-business-filter">
            <el-option v-for="item in businessOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="statusInput" class="form-view__select" placeholder="状态" clearable data-test="form-status-filter">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
          <el-button type="primary" data-test="form-search" @click="search">查询</el-button>
          <el-button data-test="form-reset" @click="resetFilter">重置</el-button>
          <span v-if="loading" class="form-view__hint">载入中…</span>
        </div>

        <el-table
          :data="pageRows"
          border
          row-key="id"
          data-test="form-table"
          @selection-change="(value: FormItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column label="业务码" min-width="140">
            <template #default="{ row }">{{ meta.businesses.find((item) => item.id === row.business_id)?.code ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="业务名称" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ businessNames[row.business_id] ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="视图组件" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">{{ row.component ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="关联菜单数" width="130" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.menu_ids.length === 0" type="warning" size="small" data-test="form-no-menu">
                0 · 无入口
              </el-tag>
              <span v-else>{{ row.menu_ids.length }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
                {{ row.status === 'enabled' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <template #empty>
            <empty-state
              type="data"
              title="暂无表单"
              description="新增表单后在此查看（双击行打开记录页签）。"
              :action="{ text: '去创建', type: 'primary' }"
              @action="openCreate"
            />
          </template>
        </el-table>

        <div class="form-view__foot">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="filteredRows.length"
            layout="total, prev, pager, next"
          />
        </div>
      </template>

      <template #record="{ tab }">
        <form-record-tab
          v-if="tab"
          :key="tab.key"
          :form-id="String(tab.key).replace('record:', '')"
          @saved="onSaved"
          @removed="onRemoved"
          @dirty="(value: boolean) => onRecordDirty(tab.key, value)"
          @close="closeTab(tab.key)"
        />
      </template>
    </form-frame>
  </page-container>
</template>

<style scoped>
.form-view__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.form-view__side {
  display: inline-flex;
  gap: var(--bms-space-3);
  align-items: center;
  margin-left: auto;
}

.form-view__filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.form-view__kw {
  width: 240px;
}

.form-view__select {
  width: 180px;
}

.form-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.form-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}
</style>
