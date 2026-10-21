<script setup lang="ts">
// 权限码管理页：权限码（业务码 × 动作码组合）列表 + 手工新增 + 批量补生成 + 批量启停删除。
// 对照原型《10_菜单管理/04_权限码管理.html》：三段式、无操作列、双击行开记录 Tab；
// 「补生成缺失组合」为原型迭代记录中登记的增强（需求 07-17 决策 5）。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { MetaStatus } from '@/api/menuMeta'
import {
  deletePermission,
  generatePermissions,
  updatePermission,
  type PermissionGeneratePayload,
  type PermissionItem,
} from '@/api/permission'
import { recordTabKey, useTabsStore } from '@/stores/tabs'
import { useMenuMetaStore } from '@/stores/menuMeta'

import GenerateDialog from './GenerateDialog.vue'
import PermissionRecordTab from './PermissionRecordTab.vue'

defineOptions({ name: 'SystemPermission' })

/** 列表页签键。 */
const LIST_KEY = 'list'
/** 每页条数。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()
const meta = useMenuMetaStore()
const router = useRouter()

/** 全量权限码。 */
const rows = ref<PermissionItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 假数据生成中。 */
const generating = ref(false)
/** 列表多选。 */
const selection = ref<PermissionItem[]>([])
/** 关键字输入。 */
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
/** 补生成对话框可见。 */
const generateVisible = ref(false)

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
/** 业务码选项。 */
const businessOptions = computed(() =>
  meta.businesses.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
)
/** 过滤后的行。 */
const filteredRows = computed(() => {
  const needle = applied.value.keyword.trim().toLowerCase()
  return rows.value.filter(
    (row) =>
      (needle === '' || row.code.toLowerCase().includes(needle) || row.name.toLowerCase().includes(needle)) &&
      (applied.value.businessId === '' || row.business_id === applied.value.businessId) &&
      (applied.value.status === '' || row.status === applied.value.status),
  )
})
/** 当前页行。 */
const pageRows = computed(() => filteredRows.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

/**
 * 载入权限码与业务码清单。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([meta.ensurePermissions(true), meta.ensureBusinesses(), meta.ensureActions()])
    rows.value = meta.permissions
    selection.value = []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '权限码列表加载失败')
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
 * @param row 权限码行。
 */
function openRecord(row: PermissionItem): void {
  tabs.open(recordTabKey(row.id), row.code)
}

/**
 * 新增权限码（手工组合）。
 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增权限码')
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
 * 提交补生成并回显计数。
 *
 * @param payload 范围与是否含停用项。
 */
async function onGenerate(payload: PermissionGeneratePayload): Promise<void> {
  generating.value = true
  try {
    const result = await generatePermissions(payload)
    ElMessage.success(`补生成完成：新建 ${result.created} / 恢复 ${result.restored} / 跳过 ${result.skipped}`)
    generateVisible.value = false
    await load()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '补生成失败')
  } finally {
    generating.value = false
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
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个权限码？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deletePermission(row.id)
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${row.code}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个权限码`)
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
      await updatePermission(row.id, { status: next })
      changed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `状态更新失败：${row.code}`)
    }
  }
  if (changed > 0) {
    ElMessage.success(`已更新 ${changed} 个权限码的状态`)
    await load()
  }
}

/**
 * 记录保存成功：新增态换为实体页签，编辑态同步标题并刷新列表。
 *
 * @param item 保存后的权限码。
 */
function onSaved(item: PermissionItem): void {
  const key = recordTabKey(item.id)
  if (tabs.active === recordTabKey('new')) {
    tabs.discard(recordTabKey('new'))
    tabs.open(key, item.code)
  } else {
    const tab = tabs.tabOf(key)
    if (tab !== undefined) {
      tab.title = item.code
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
  tabs.reset(LIST_KEY, '权限码管理')
  void load()
})
</script>

<template>
  <page-container title="权限码管理" description="权限码 = 业务码 × 动作码组合（受控可授项）：平台统一维护、租户只读">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="permission-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="permission-view__toolbar">
          <el-button type="primary" data-test="permission-create" @click="openCreate">新增</el-button>
          <el-button :loading="generating" data-test="permission-generate" @click="generateVisible = true">
            补生成缺失组合
          </el-button>
          <el-button data-test="permission-refresh" @click="load">刷新</el-button>
          <el-button data-test="permission-close-page" @click="closePage">关闭</el-button>
          <el-button type="danger" plain :disabled="selection.length === 0" data-test="permission-batch-delete" @click="removeSelected">
            删除
          </el-button>
          <el-button :disabled="selection.length === 0" data-test="permission-batch-toggle" @click="toggleSelected">
            停用/启用
          </el-button>
          <span class="permission-view__side">
            <el-button disabled title="导出能力本期未立项（置灰占位）" data-test="permission-export">导出</el-button>
            <span class="permission-view__hint">平台超管维护 · 租户只读（40204）</span>
          </span>
        </div>

        <div class="permission-view__filter">
          <el-input
            v-model="keyword"
            class="permission-view__kw"
            placeholder="关键字：权限码/名称"
            clearable
            data-test="permission-kw"
            @keyup.enter="search"
          />
          <el-select v-model="businessInput" class="permission-view__select" placeholder="业务码" clearable filterable data-test="permission-business-filter">
            <el-option v-for="item in businessOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="statusInput" class="permission-view__select" placeholder="状态" clearable data-test="permission-status-filter">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
          <el-button type="primary" data-test="permission-search" @click="search">查询</el-button>
          <el-button data-test="permission-reset" @click="resetFilter">重置</el-button>
          <span v-if="loading" class="permission-view__hint">载入中…</span>
        </div>

        <el-table
          :data="pageRows"
          border
          row-key="id"
          data-test="permission-table"
          @selection-change="(value: PermissionItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column prop="code" label="权限码" min-width="160" />
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="business_code" label="业务码" min-width="140" />
          <el-table-column prop="action_code" label="动作码" min-width="130" />
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
              title="暂无权限码"
              description="手工新增组合或「补生成缺失组合」后在此查看（双击行打开记录页签）。"
              :action="{ text: '去创建', type: 'primary' }"
              @action="openCreate"
            />
          </template>
        </el-table>

        <div class="permission-view__foot">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="filteredRows.length"
            layout="total, prev, pager, next"
          />
        </div>

        <generate-dialog
          v-model="generateVisible"
          :businesses="meta.businesses"
          :actions="meta.actions"
          @submit="onGenerate"
        />
      </template>

      <template #record="{ tab }">
        <permission-record-tab
          v-if="tab"
          :key="tab.key"
          :permission-id="String(tab.key).replace('record:', '')"
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
.permission-view__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.permission-view__side {
  display: inline-flex;
  gap: var(--bms-space-3);
  align-items: center;
  margin-left: auto;
}

.permission-view__filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.permission-view__kw {
  width: 240px;
}

.permission-view__select {
  width: 180px;
}

.permission-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.permission-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}
</style>
