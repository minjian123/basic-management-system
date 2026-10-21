<script setup lang="ts">
// 业务码管理页：业务码字典（纯资源维度）列表 + 批量启停删除。
// 对照原型《10_菜单管理/08_业务码管理.html》：三段式、无操作列、双击行开记录 Tab、20 条/页。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { deleteBusiness, updateBusiness, type BusinessItem } from '@/api/business'
import type { MetaStatus } from '@/api/menuMeta'
import { recordTabKey, useTabsStore } from '@/stores/tabs'
import { useMenuMetaStore } from '@/stores/menuMeta'

import BusinessRecordTab from './BusinessRecordTab.vue'

defineOptions({ name: 'SystemBusiness' })

/** 列表页签键。 */
const LIST_KEY = 'list'
/** 每页条数。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()
const meta = useMenuMetaStore()
const router = useRouter()

/** 全量业务码。 */
const rows = ref<BusinessItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 列表多选。 */
const selection = ref<BusinessItem[]>([])
/** 关键字输入。 */
const keyword = ref('')
/** 状态输入。 */
const statusInput = ref<'' | MetaStatus>('')
/** 已应用筛选。 */
const applied = ref<{ keyword: string; status: '' | MetaStatus }>({ keyword: '', status: '' })
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
/** 过滤后的行。 */
const filteredRows = computed(() => {
  const needle = applied.value.keyword.trim().toLowerCase()
  return rows.value.filter(
    (row) =>
      (needle === '' || row.code.toLowerCase().includes(needle) || row.name.toLowerCase().includes(needle)) &&
      (applied.value.status === '' || row.status === applied.value.status),
  )
})
/** 当前页行。 */
const pageRows = computed(() => filteredRows.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

/**
 * 载入业务码清单。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    await meta.ensureBusinesses(true)
    rows.value = meta.businesses
    selection.value = []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '业务码列表加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 应用筛选（回第一页）。
 */
function search(): void {
  applied.value = { keyword: keyword.value, status: statusInput.value }
  page.value = 1
}

/**
 * 重置筛选。
 */
function resetFilter(): void {
  keyword.value = ''
  statusInput.value = ''
  applied.value = { keyword: '', status: '' }
  page.value = 1
}

/**
 * 打开记录页签。
 *
 * @param row 业务码行。
 */
function openRecord(row: BusinessItem): void {
  tabs.open(recordTabKey(row.id), `${row.code} · ${row.name}`)
}

/**
 * 新增业务码。
 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增业务码')
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
 * 批量删除（逐行执行并汇总；被引用 `40206` 逐条提示）。
 */
async function removeSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个业务码？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deleteBusiness(row.id)
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${row.code}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个业务码`)
    await load()
  }
}

/**
 * 批量停用 / 启用（停用联动其权限码；被引用整批拒绝 `40206`）。
 */
async function toggleSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  let changed = 0
  for (const row of selection.value) {
    const next: MetaStatus = row.status === 'enabled' ? 'disabled' : 'enabled'
    try {
      await updateBusiness(row.id, { status: next, i18n: row.i18n })
      changed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `状态更新失败：${row.code}`)
    }
  }
  if (changed > 0) {
    ElMessage.success(`已更新 ${changed} 个业务码的状态`)
    await load()
  }
}

/**
 * 记录保存成功：新增态换为实体页签，编辑态同步标题并刷新列表。
 *
 * @param item 保存后的业务码。
 */
function onSaved(item: BusinessItem): void {
  const key = recordTabKey(item.id)
  const title = `${item.code} · ${item.name}`
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
  tabs.reset(LIST_KEY, '业务码管理')
  void load()
})
</script>

<template>
  <page-container title="业务码管理" description="业务码字典（纯资源维度）：与动作码组合成权限码，平台统一维护、租户只读">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="business-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="business-view__toolbar">
          <el-button type="primary" data-test="business-create" @click="openCreate">新增</el-button>
          <el-button data-test="business-refresh" @click="load">刷新</el-button>
          <el-button data-test="business-close-page" @click="closePage">关闭</el-button>
          <el-button type="danger" plain :disabled="selection.length === 0" data-test="business-batch-delete" @click="removeSelected">
            删除
          </el-button>
          <el-button :disabled="selection.length === 0" data-test="business-batch-toggle" @click="toggleSelected">
            停用/启用
          </el-button>
          <span class="business-view__side">
            <el-button disabled title="导出能力本期未立项（置灰占位）" data-test="business-export">导出</el-button>
            <span class="business-view__hint">平台超管维护 · 租户只读（40204）</span>
          </span>
        </div>

        <div class="business-view__filter">
          <el-input
            v-model="keyword"
            class="business-view__kw"
            placeholder="关键字：业务码/名称"
            clearable
            data-test="business-kw"
            @keyup.enter="search"
          />
          <el-select v-model="statusInput" class="business-view__select" placeholder="状态" clearable data-test="business-status-filter">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
          <el-button type="primary" data-test="business-search" @click="search">查询</el-button>
          <el-button data-test="business-reset" @click="resetFilter">重置</el-button>
          <span v-if="loading" class="business-view__hint">载入中…</span>
        </div>

        <el-table
          :data="pageRows"
          border
          row-key="id"
          data-test="business-table"
          @selection-change="(value: BusinessItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column prop="code" label="业务码" min-width="160" />
          <el-table-column prop="name" label="名称" min-width="220" />
          <el-table-column prop="permission_count" label="权限码数" width="110" />
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
              title="暂无业务码"
              description="新增业务码后在此查看（双击行打开记录页签）。"
              :action="{ text: '去创建', type: 'primary' }"
              @action="openCreate"
            />
          </template>
        </el-table>

        <div class="business-view__foot">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="filteredRows.length"
            layout="total, prev, pager, next"
          />
        </div>
      </template>

      <template #record="{ tab }">
        <business-record-tab
          v-if="tab"
          :key="tab.key"
          :business-id="String(tab.key).replace('record:', '')"
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
.business-view__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.business-view__side {
  display: inline-flex;
  gap: var(--bms-space-3);
  align-items: center;
  margin-left: auto;
}

.business-view__filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.business-view__kw {
  width: 240px;
}

.business-view__select {
  width: 160px;
}

.business-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.business-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}
</style>
