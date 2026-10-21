<script setup lang="ts">
// 动作码管理页：动作码字典（全局动词维度、不归属业务）列表 + 批量启停删除。
// 对照原型《10_菜单管理/09_动作码管理.html》：三段式、无操作列、双击行开记录 Tab、20 条/页。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { deleteAction, listActions, updateAction, type ActionItem } from '@/api/action'
import type { MetaStatus } from '@/api/menuMeta'
import { recordTabKey, useTabsStore } from '@/stores/tabs'

import ActionRecordTab from './ActionRecordTab.vue'

defineOptions({ name: 'SystemAction' })

/** 列表页签键。 */
const LIST_KEY = 'list'
/** 每页条数。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()
const router = useRouter()

/** 全量动作码。 */
const rows = ref<ActionItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 列表多选。 */
const selection = ref<ActionItem[]>([])
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
 * 载入动作码清单。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = (await listActions()).items
    selection.value = []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '动作码列表加载失败')
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
 * @param row 动作码行。
 */
function openRecord(row: ActionItem): void {
  tabs.open(recordTabKey(row.id), `${row.code} · ${row.name}`)
}

/**
 * 新增动作码。
 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增动作码')
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
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个动作码？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deleteAction(row.id)
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${row.code}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个动作码`)
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
      await updateAction(row.id, { status: next, i18n: row.i18n })
      changed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `状态更新失败：${row.code}`)
    }
  }
  if (changed > 0) {
    ElMessage.success(`已更新 ${changed} 个动作码的状态`)
    await load()
  }
}

/**
 * 记录保存成功：新增态换为实体页签，编辑态同步标题并刷新列表。
 *
 * @param item 保存后的动作码。
 */
function onSaved(item: ActionItem): void {
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
  tabs.reset(LIST_KEY, '动作码管理')
  void load()
})
</script>

<template>
  <page-container title="动作码管理" description="动作码字典（全局动词维度）：与业务码组合成权限码，平台统一维护、租户只读">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="action-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="action-view__toolbar">
          <el-button type="primary" data-test="action-create" @click="openCreate">新增</el-button>
          <el-button data-test="action-refresh" @click="load">刷新</el-button>
          <el-button data-test="action-close-page" @click="closePage">关闭</el-button>
          <el-button type="danger" plain :disabled="selection.length === 0" data-test="action-batch-delete" @click="removeSelected">
            删除
          </el-button>
          <el-button :disabled="selection.length === 0" data-test="action-batch-toggle" @click="toggleSelected">
            停用/启用
          </el-button>
          <span class="action-view__side">
            <el-button disabled title="导出能力本期未立项（置灰占位）" data-test="action-export">导出</el-button>
            <span class="action-view__hint">平台超管维护 · 租户只读（40204）</span>
          </span>
        </div>

        <div class="action-view__filter">
          <el-input
            v-model="keyword"
            class="action-view__kw"
            placeholder="关键字：动作码/名称"
            clearable
            data-test="action-kw"
            @keyup.enter="search"
          />
          <el-select v-model="statusInput" class="action-view__select" placeholder="状态" clearable data-test="action-status-filter">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
          <el-button type="primary" data-test="action-search" @click="search">查询</el-button>
          <el-button data-test="action-reset" @click="resetFilter">重置</el-button>
          <span v-if="loading" class="action-view__hint">载入中…</span>
        </div>

        <el-table
          :data="pageRows"
          border
          row-key="id"
          data-test="action-table"
          @selection-change="(value: ActionItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column prop="code" label="动作码" min-width="160" />
          <el-table-column prop="name" label="名称" min-width="220" />
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
              title="暂无动作码"
              description="新增动作码后在此查看（双击行打开记录页签）。"
              :action="{ text: '去创建', type: 'primary' }"
              @action="openCreate"
            />
          </template>
        </el-table>

        <div class="action-view__foot">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="filteredRows.length"
            layout="total, prev, pager, next"
          />
        </div>
      </template>

      <template #record="{ tab }">
        <action-record-tab
          v-if="tab"
          :key="tab.key"
          :action-id="String(tab.key).replace('record:', '')"
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
.action-view__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.action-view__side {
  display: inline-flex;
  gap: var(--bms-space-3);
  align-items: center;
  margin-left: auto;
}

.action-view__filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.action-view__kw {
  width: 240px;
}

.action-view__select {
  width: 160px;
}

.action-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.action-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}
</style>
