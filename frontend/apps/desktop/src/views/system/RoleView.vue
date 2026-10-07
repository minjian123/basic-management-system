<script setup lang="ts">
// 角色管理页（平台内建页）：表单框架宿主——列表 Tab（固定不可关）+ 记录 Tab（新增 / 双击行打开）。
// 结构对照原型《09_角色管理/02_角色列表页.html》《03_角色表单页.html》：列表三段式**无操作列** + 批量删除 +
// 内置标记；记录页三子页签与工具栏单一保存见 `RoleRecordTab`。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { deleteRole, listRoles, type RoleItem } from '@/api/role'
import { recordTabKey, useTabsStore } from '@/stores/tabs'

import RoleRecordTab from './RoleRecordTab.vue'

defineOptions({ name: 'SystemRole' })

/** 列表页签键（固定不可关）。 */
const LIST_KEY = 'list'
/** 每页条数（缺省 20）。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()

/** 列表数据。 */
const rows = ref<RoleItem[]>([])
/** 总数。 */
const total = ref(0)
/** 当前页。 */
const page = ref(1)
/** 关键字（角色码 / 名称）。 */
const keyword = ref('')
/** 状态筛选。 */
const status = ref('')
/** 载入中。 */
const loading = ref(false)
/** 列表多选。 */
const selection = ref<RoleItem[]>([])

/** 表单框架页签（映射 store 状态）。 */
const frameTabs = computed<FormFrameTab[]>(() =>
  tabs.tabs.map((tab) => ({ key: tab.key, title: tab.title, type: tab.type, closable: tab.closable, dirty: tab.dirty })),
)

/** 当前激活页签键。 */
const activeKey = computed(() => tabs.active)

/**
 * 载入角色列表（关键字 / 状态 + 分页）。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listRoles({
      kw: keyword.value || undefined,
      status: status.value || undefined,
      page: page.value,
      size: PAGE_SIZE,
    })
    rows.value = data.list ?? []
    total.value = data.total ?? 0
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '角色列表加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 检索（回第一页）。
 */
function search(): void {
  page.value = 1
  void load()
}

/**
 * 打开记录页签（双击行）。
 *
 * @param row 角色行。
 */
function openRecord(row: RoleItem): void {
  tabs.open(recordTabKey(String(row.id)), `${row.name ?? ''}（${row.code ?? ''}）`)
}

/**
 * 新增角色（记录页签新增态）。
 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增角色')
}

/**
 * 关闭页签（脏数据拦截：确认后丢弃变更关闭）。
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
 * 批量删除（内置角色禁删由后端 30043 拦截，逐一执行并汇总）。
 */
async function removeSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个角色？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deleteRole(String(row.id))
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${row.code ?? ''}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个角色`)
    selection.value = []
    await load()
  }
}

/**
 * 记录保存成功回调（刷新列表并同步记录页签标题）。
 *
 * @param role 保存后的角色详情。
 */
function onSaved(role: { id?: string; name?: string; code?: string }): void {
  const key = recordTabKey(String(role.id ?? ''))
  const tab = tabs.tabOf(key)
  if (tab !== undefined) {
    tab.title = `${role.name ?? ''}（${role.code ?? ''}）`
  }
  tabs.activate(key)
  void load()
}

/**
 * 记录页签脏态同步（页签显示未保存标记）。
 *
 * @param key 页签键。
 * @param dirty 是否脏。
 */
function onRecordDirty(key: string, dirty: boolean): void {
  tabs.setDirty(key, dirty)
}

onMounted(() => {
  tabs.reset(LIST_KEY, '角色管理')
  void load()
})
</script>

<template>
  <page-container title="角色管理" description="角色定义与授予：菜单 / 表单 / 操作 / 字段与数据权限挂角色、经分配落到用户">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="role-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="role-view__toolbar">
          <el-button type="primary" data-test="role-create" @click="openCreate">新增</el-button>
          <el-button :disabled="selection.length === 0" data-test="role-batch-delete" @click="removeSelected">
            批量删除
          </el-button>
        </div>

        <div class="role-view__filter">
          <el-input
            v-model="keyword"
            class="role-view__kw"
            placeholder="角色码 / 名称"
            clearable
            data-test="role-kw"
            @keyup.enter="search"
          />
          <el-select v-model="status" class="role-view__status" placeholder="状态" clearable data-test="role-status">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
          <el-button data-test="role-search" @click="search">查询</el-button>
          <span v-if="loading" class="role-view__hint">载入中…</span>
        </div>

        <el-table
          :data="rows"
          border
          row-key="id"
          data-test="role-table"
          @selection-change="(value: RoleItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column prop="code" label="角色码" min-width="140" />
          <el-table-column prop="name" label="角色名" min-width="160" />
          <el-table-column label="内置" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.builtin" type="warning" size="small" data-test="role-builtin-tag">内置</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="subject_count" label="主体数" width="100" />
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
              title="暂无角色"
              description="点击「新增」创建角色后在此查看（双击行打开记录页签）。"
            />
          </template>
        </el-table>

        <div class="role-view__foot">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="total"
            layout="total, prev, pager, next"
            @current-change="load"
          />
        </div>
      </template>

      <template #record="{ tab }">
        <role-record-tab
          v-if="tab"
          :key="tab.key"
          :role-id="String(tab.key).replace('record:', '')"
          @saved="onSaved"
          @dirty="(value: boolean) => onRecordDirty(tab.key, value)"
          @close="tabs.discard(tab.key)"
        />
      </template>
    </form-frame>
  </page-container>
</template>

<style scoped>
.role-view__toolbar {
  display: flex;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.role-view__filter {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.role-view__kw {
  width: 220px;
}

.role-view__status {
  width: 140px;
}

.role-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.role-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}
</style>
