<script setup lang="ts">
// 自定义图标管理页：租户自定义图标（`sys_icon`）列表 + icon key 复制 + 引用计数 + 批量启停删除。
// 对照原型《10_菜单管理/06_自定义图标管理.html》：三段式、无操作列、双击行开记录 Tab；仅管理租户自定义图标。
import { EmptyState, FormFrame, IconRenderer, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { deleteIcon, updateIcon, type IconItem, type IconStatus } from '@/api/icon'
import { recordTabKey, useTabsStore } from '@/stores/tabs'
import { useMenuMetaStore } from '@/stores/menuMeta'

import IconRecordTab from './IconRecordTab.vue'

defineOptions({ name: 'SystemIcon' })

/** 列表页签键。 */
const LIST_KEY = 'list'
/** 每页条数。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()
const meta = useMenuMetaStore()
const router = useRouter()

/** 全量图标。 */
const rows = ref<IconItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 列表多选。 */
const selection = ref<IconItem[]>([])
/** 关键字输入。 */
const keyword = ref('')
/** 分组输入。 */
const categoryInput = ref('')
/** 状态输入。 */
const statusInput = ref<'' | IconStatus>('')
/** 已应用筛选。 */
const applied = ref<{ keyword: string; category: string; status: '' | IconStatus }>({
  keyword: '',
  category: '',
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
/** 分组候选。 */
const categories = computed(() => [...new Set(rows.value.map((row) => row.category))].sort())
/** 过滤后的行。 */
const filteredRows = computed(() => {
  const needle = applied.value.keyword.trim().toLowerCase()
  return rows.value.filter(
    (row) =>
      (needle === '' ||
        row.code.toLowerCase().includes(needle) ||
        row.name.toLowerCase().includes(needle) ||
        row.tags.some((tag) => tag.toLowerCase().includes(needle))) &&
      (applied.value.category === '' || row.category === applied.value.category) &&
      (applied.value.status === '' || row.status === applied.value.status),
  )
})
/** 当前页行。 */
const pageRows = computed(() => filteredRows.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

/**
 * 载入图标清单（装载时同步登记到图标注册表，供预览 / 选择器消费）。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    await meta.ensureIcons(true)
    rows.value = meta.icons
    selection.value = []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '图标列表加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 应用筛选（回第一页）。
 */
function search(): void {
  applied.value = { keyword: keyword.value, category: categoryInput.value, status: statusInput.value }
  page.value = 1
}

/**
 * 重置筛选。
 */
function resetFilter(): void {
  keyword.value = ''
  categoryInput.value = ''
  statusInput.value = ''
  applied.value = { keyword: '', category: '', status: '' }
  page.value = 1
}

/**
 * 复制 icon key。
 *
 * @param row 图标行。
 */
async function copyKey(row: IconItem): Promise<void> {
  try {
    if (navigator.clipboard === undefined) {
      throw new Error('clipboard unavailable')
    }
    await navigator.clipboard.writeText(row.icon_key)
    ElMessage.success('已复制 icon key')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

/**
 * 打开记录页签。
 *
 * @param row 图标行。
 */
function openRecord(row: IconItem): void {
  tabs.open(recordTabKey(row.code), `${row.name}（${row.icon_key}）`)
}

/**
 * 新增图标。
 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增自定义图标')
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
 * 批量删除（引用检查：被菜单引用时 `40206`）。
 */
async function removeSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个图标？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deleteIcon(row.code)
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${row.code}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个图标`)
    await load()
  }
}

/**
 * 批量停用 / 启用。
 */
async function toggleSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  let changed = 0
  for (const row of selection.value) {
    const next: IconStatus = row.status === 'active' ? 'disabled' : 'active'
    try {
      await updateIcon(row.code, { status: next })
      changed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `状态更新失败：${row.code}`)
    }
  }
  if (changed > 0) {
    ElMessage.success(`已更新 ${changed} 个图标的状态`)
    await load()
  }
}

/**
 * 记录保存成功：新增态换为实体页签，编辑态同步标题并刷新列表。
 *
 * @param item 保存后的图标。
 */
function onSaved(item: IconItem): void {
  const key = recordTabKey(item.code)
  const title = `${item.name}（${item.icon_key}）`
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
  tabs.reset(LIST_KEY, '自定义图标')
  void load()
})
</script>

<template>
  <page-container title="自定义图标" description="租户自定义图标（sys_icon）：SVG 上传、多语言名称、引用计数与启停">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="icon-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="icon-view__toolbar">
          <el-button type="primary" data-test="icon-create" @click="openCreate">新增</el-button>
          <el-button data-test="icon-refresh" @click="load">刷新</el-button>
          <el-button data-test="icon-close-page" @click="closePage">关闭</el-button>
          <el-button type="danger" plain :disabled="selection.length === 0" data-test="icon-batch-delete" @click="removeSelected">
            删除
          </el-button>
          <el-button :disabled="selection.length === 0" data-test="icon-batch-toggle" @click="toggleSelected">
            停用/启用
          </el-button>
          <span class="icon-view__side">
            <el-button disabled title="导出能力本期未立项（置灰占位）" data-test="icon-export">导出</el-button>
            <span class="icon-view__hint">需 icon:manage（默认归属系统管理员）</span>
          </span>
        </div>

        <div class="icon-view__filter">
          <el-input
            v-model="keyword"
            class="icon-view__kw"
            placeholder="关键字：图标键/名称/标签"
            clearable
            data-test="icon-kw"
            @keyup.enter="search"
          />
          <el-select v-model="categoryInput" class="icon-view__select" placeholder="分组" clearable data-test="icon-category-filter">
            <el-option v-for="item in categories" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select v-model="statusInput" class="icon-view__select" placeholder="状态" clearable data-test="icon-status-filter">
            <el-option label="启用" value="active" />
            <el-option label="停用" value="disabled" />
          </el-select>
          <el-button type="primary" data-test="icon-search" @click="search">查询</el-button>
          <el-button data-test="icon-reset" @click="resetFilter">重置</el-button>
          <span v-if="loading" class="icon-view__hint">载入中…</span>
        </div>

        <el-table
          :data="pageRows"
          border
          row-key="id"
          data-test="icon-table"
          @selection-change="(value: IconItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column label="图标" width="80" align="center">
            <template #default="{ row }">
              <icon-renderer :name="row.icon_key" :size="18" />
            </template>
          </el-table-column>
          <el-table-column label="图标键" min-width="200">
            <template #default="{ row }">
              <code>{{ row.icon_key }}</code>
              <el-button link type="primary" size="small" data-test="icon-copy" @click.stop="copyKey(row)">复制</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="150" />
          <el-table-column prop="category" label="分组" width="110" />
          <el-table-column label="引用计数" width="110" align="center">
            <template #default="{ row }">{{ row.reference_count }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === 'active' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <template #empty>
            <empty-state
              type="data"
              title="暂无自定义图标"
              description="新增图标后在此查看（双击行打开记录页签）。"
              :action="{ text: '去创建', type: 'primary' }"
              @action="openCreate"
            />
          </template>
        </el-table>

        <div class="icon-view__foot">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="filteredRows.length"
            layout="total, prev, pager, next"
          />
        </div>
      </template>

      <template #record="{ tab }">
        <icon-record-tab
          v-if="tab"
          :key="tab.key"
          :icon-code="String(tab.key).replace('record:', '')"
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
.icon-view__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.icon-view__side {
  display: inline-flex;
  gap: var(--bms-space-3);
  align-items: center;
  margin-left: auto;
}

.icon-view__filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.icon-view__kw {
  width: 240px;
}

.icon-view__select {
  width: 160px;
}

.icon-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.icon-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}
</style>
