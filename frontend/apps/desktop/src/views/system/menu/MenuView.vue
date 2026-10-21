<script setup lang="ts">
// 菜单管理页（平台内建页）：列表 Tab（固定不可关）+ 菜单记录 Tab（新增 / 双击行打开）。
// 对照原型《10_菜单管理/02_菜单维护页.html》：三段式、树形表格、无操作列、行首 ⋮⋮ 拖拽调序
// （拖到手柄＝同级并排其后，拖到菜单名称＝成为其子级，仅目录可容纳下级），工具栏「保存排序 / 撤销」。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { deleteMenu, updateMenu, type MenuItem, type MenuPayload } from '@/api/menuMeta'
import { MENU_EXPANDED_STORAGE_KEY } from '@/composables/useMenuExpanded'
import { recordTabKey, useTabsStore } from '@/stores/tabs'
import { useMenuMetaStore } from '@/stores/menuMeta'

import MenuRecordTab from './MenuRecordTab.vue'
import {
  countMenus,
  expandableIds,
  expandIdsForKeyword,
  filterMenus,
  findMenu,
  firstLevelExpandableIds,
  flattenMenus,
  menuTypeOf,
  reorderMenus,
  type DropPosition,
  type MenuFilter,
  type MenuMove,
} from './menuTree'

defineOptions({ name: 'SystemMenu' })

/** 列表页签键（固定不可关）。 */
const LIST_KEY = 'list'
/** 默认全展开的节点数阈值。 */
const EXPAND_THRESHOLD = 50

const tabs = useTabsStore()
const meta = useMenuMetaStore()
const router = useRouter()

/** 全量菜单树。 */
const rows = ref<MenuItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 保存排序中。 */
const savingSort = ref(false)
/** 列表多选。 */
const selection = ref<MenuItem[]>([])
/** 关键字输入。 */
const keyword = ref('')
/** 菜单类型输入。 */
const typeInput = ref<'' | 'directory' | 'menu'>('')
/** 状态输入。 */
const statusInput = ref<'' | 'enabled' | 'disabled'>('')
/** 已应用的筛选条件。 */
const applied = ref<MenuFilter>({})
/** 待提交的排序变更。 */
const pendingMoves = ref<MenuMove[]>([])
/** 被拖节点 ID。 */
const draggingId = ref('')
/** 拖拽落点提示。 */
const dropHint = ref<{ id: string; position: DropPosition } | null>(null)
/** 已展开节点 ID（用户偏好）。 */
const expandedIds = ref<string[]>([])
/** 程序化展开中（忽略 expand-change 回写）。 */
const applying = ref(false)
/** 表格实例（树形展开控制）。 */
const tableRef = ref<{ toggleRowExpansion: (row: MenuItem, expanded: boolean) => void } | null>(null)

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
/** 过滤后的树。 */
const filteredTree = computed(() => filterMenus(rows.value, applied.value))
/** 全部可展开节点。 */
const expandables = computed(() => expandableIds(rows.value))
/** 是否已全部展开。 */
const allExpanded = computed(
  () => expandables.value.length > 0 && expandables.value.every((id) => expandedIds.value.includes(id)),
)
/** 是否有未保存排序变更。 */
const sortDirty = computed(() => pendingMoves.value.length > 0)
/** 工具栏展开 / 折叠文案。 */
const expandText = computed(() => (allExpanded.value ? '全部折叠' : '全部展开'))

/**
 * 菜单节点 → 更新载荷（可覆盖状态 / 排序）。
 *
 * @param node 菜单节点。
 * @param overrides 覆盖字段。
 * @returns 更新载荷。
 */
function nodePayload(node: MenuItem, overrides: Partial<MenuPayload> = {}): MenuPayload {
  return {
    parent_id: node.parent_id,
    path: node.path,
    component: node.component ?? null,
    icon: node.icon ?? null,
    sort: node.sort,
    hidden: node.hidden,
    status: node.status === 'disabled' ? 'disabled' : 'enabled',
    i18n: node.i18n,
    ...overrides,
  }
}

/**
 * 读取本地展开偏好。
 *
 * @returns 展开 ID 清单；无偏好返回 `null`。
 */
function readExpandedPreference(): string[] | null {
  try {
    const raw = localStorage.getItem(MENU_EXPANDED_STORAGE_KEY)
    if (raw === null) {
      return null
    }
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return null
    }
    return parsed.filter((item): item is string => typeof item === 'string')
  } catch {
    return null
  }
}

/**
 * 写入本地展开偏好（存储不可用不阻断交互）。
 *
 * @param ids 展开 ID 清单。
 */
function writeExpandedPreference(ids: readonly string[]): void {
  try {
    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, JSON.stringify(ids))
  } catch {
    // 忽略存储异常
  }
}

/**
 * 把展开集合应用到树形表格（程序化切换不触发偏好回写）。
 *
 * @param ids 应展开的节点 ID。
 */
function applyExpansion(ids: readonly string[]): void {
  const table = tableRef.value
  if (table === null) {
    return
  }
  applying.value = true
  const expandable = new Set(expandableIds(rows.value))
  for (const node of flattenMenus(rows.value)) {
    if (expandable.has(node.id)) {
      table.toggleRowExpansion(node, ids.includes(node.id))
    }
  }
  void nextTick(() => {
    applying.value = false
  })
}

/**
 * 载入菜单树并按规模 / 本地偏好初始化展开状态。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    await meta.ensureMenus(true)
    rows.value = meta.menus
    pendingMoves.value = []
    selection.value = []
    const stored = readExpandedPreference()
    expandedIds.value =
      stored ?? (countMenus(rows.value) <= EXPAND_THRESHOLD ? expandableIds(rows.value) : firstLevelExpandableIds(rows.value))
    await nextTick()
    applyExpansion(expandedIds.value)
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '菜单列表加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 应用筛选（关键字 / 类型 / 状态）。
 */
function search(): void {
  applied.value = {
    keyword: keyword.value,
    type: typeInput.value,
    status: statusInput.value,
  }
}

/**
 * 重置筛选。
 */
function resetFilter(): void {
  keyword.value = ''
  typeInput.value = ''
  statusInput.value = ''
  applied.value = {}
}

/**
 * 展开 / 折叠全部可展开节点。
 */
function toggleExpandAll(): void {
  expandedIds.value = allExpanded.value ? [] : expandableIds(rows.value)
  writeExpandedPreference(expandedIds.value)
  applyExpansion(expandedIds.value)
}

/**
 * 行内展开 / 收起回写偏好（筛选态下的临时展开不写偏好）。
 *
 * @param row 行。
 * @param expanded 是否展开。
 */
function onExpandChange(row: MenuItem, expanded: boolean): void {
  if (applying.value) {
    return
  }
  const set = new Set(expandedIds.value)
  if (expanded) {
    set.add(row.id)
  } else {
    set.delete(row.id)
  }
  expandedIds.value = [...set]
  if ((applied.value.keyword ?? '') === '') {
    writeExpandedPreference(expandedIds.value)
  }
}

/**
 * 拖拽开始。
 *
 * @param event 拖拽事件。
 * @param row 被拖节点。
 */
function onDragStart(event: Event, row: MenuItem): void {
  draggingId.value = row.id
  ;(event as DragEvent).dataTransfer?.setData('text/plain', row.id)
}

/**
 * 拖拽结束（清理提示）。
 */
function onDragEnd(): void {
  draggingId.value = ''
  dropHint.value = null
}

/**
 * 拖拽经过目标（记录落点提示）。
 *
 * @param row 目标节点。
 * @param position 落位。
 */
function onDragOver(row: MenuItem, position: DropPosition): void {
  if (draggingId.value === '' || draggingId.value === row.id) {
    return
  }
  dropHint.value = { id: row.id, position }
}

/**
 * 拖拽释放（本地乐观更新 + 记录待提交变更）。
 *
 * @param row 目标节点。
 * @param position 落位。
 */
function onDrop(row: MenuItem, position: DropPosition): void {
  const dragId = draggingId.value
  draggingId.value = ''
  dropHint.value = null
  if (dragId === '') {
    return
  }
  const result = reorderMenus(rows.value, dragId, row.id, position)
  if (result === undefined) {
    ElMessage.warning('不可拖入自身或自身子树；放入其中仅限目录节点')
    return
  }
  if (result.moves.length === 0) {
    return
  }
  rows.value = result.tree
  pendingMoves.value = result.moves
}

/**
 * 行样式（拖拽落点高亮）。
 *
 * @param payload 行上下文。
 * @returns 类名。
 */
function rowClassName(payload: { row: MenuItem }): string {
  if (dropHint.value === null || dropHint.value.id !== payload.row.id) {
    return ''
  }
  return dropHint.value.position === 'inner' ? 'menu-view__row-into' : 'menu-view__row-after'
}

/**
 * 保存排序（逐节点提交完整载荷 + 新 `parent_id` / `sort`；失败回滚）。
 */
async function saveSort(): Promise<void> {
  if (pendingMoves.value.length === 0) {
    return
  }
  savingSort.value = true
  try {
    for (const move of pendingMoves.value) {
      const node = findMenu(rows.value, move.id)
      if (node === undefined) {
        continue
      }
      await updateMenu(node.id, nodePayload(node, { parent_id: move.parent_id, sort: move.sort }))
    }
    pendingMoves.value = []
    await load()
    ElMessage.success('排序已保存')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '排序保存失败，已回滚')
    pendingMoves.value = []
    await load()
  } finally {
    savingSort.value = false
  }
}

/**
 * 撤销排序（重新拉取全树）。
 */
async function undoSort(): Promise<void> {
  pendingMoves.value = []
  await load()
}

/**
 * 打开记录页签（双击行）。
 *
 * @param row 菜单行。
 */
function openRecord(row: MenuItem): void {
  tabs.open(recordTabKey(row.id), `${row.name}（${row.path}）`)
}

/**
 * 新增菜单（记录页签新增态）。
 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增菜单')
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
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个菜单？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deleteMenu(row.id)
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${row.name}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个菜单`)
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
    const next = row.status === 'enabled' ? 'disabled' : 'enabled'
    try {
      await updateMenu(row.id, nodePayload(row, { status: next }))
      changed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `状态更新失败：${row.name}`)
    }
  }
  if (changed > 0) {
    ElMessage.success(`已更新 ${changed} 个菜单的状态`)
    await load()
  }
}

/**
 * 关闭页面（列表页签固定不可关，返回工作台）。
 */
function closePage(): void {
  void router.push('/')
}

/**
 * 记录保存成功：新增态换为实体页签，编辑态同步标题并刷新列表。
 *
 * @param menu 保存后的菜单。
 */
function onSaved(menu: MenuItem): void {
  const key = recordTabKey(menu.id)
  const title = `${menu.name}（${menu.path}）`
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

// 回到列表页签：表格重新挂载后按当前偏好恢复展开态
watch(activeKey, (key) => {
  if (key === LIST_KEY) {
    void nextTick(() => applyExpansion(expandedIds.value))
  }
})

// 筛选关键字变化：自动展开命中路径（临时展开，不写偏好）
watch(
  applied,
  () => {
    const keyword = applied.value.keyword ?? ''
    const ids =
      keyword === ''
        ? expandedIds.value
        : [...new Set([...expandedIds.value, ...expandIdsForKeyword(rows.value, keyword)])]
    void nextTick(() => applyExpansion(ids))
  },
  { deep: true },
)

onMounted(() => {
  tabs.reset(LIST_KEY, '菜单管理')
  void load()
})
</script>

<template>
  <page-container title="菜单管理" description="菜单树与挂接配置：菜单 ↔ 表单多对多、按钮挂权限码、字段挂表单">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="menu-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="menu-view__toolbar">
          <el-button type="primary" data-test="menu-create" @click="openCreate">新增</el-button>
          <el-button data-test="menu-refresh" @click="load">刷新</el-button>
          <el-button data-test="menu-close-page" @click="closePage">关闭</el-button>
          <el-button type="danger" plain :disabled="selection.length === 0" data-test="menu-batch-delete" @click="removeSelected">
            删除
          </el-button>
          <el-button :disabled="selection.length === 0" data-test="menu-batch-toggle" @click="toggleSelected">
            停用/启用
          </el-button>
          <el-button data-test="menu-expand-all" @click="toggleExpandAll">{{ expandText }}</el-button>
          <el-button type="primary" plain :disabled="!sortDirty || savingSort" data-test="menu-save-sort" @click="saveSort">
            保存排序
          </el-button>
          <el-button :disabled="!sortDirty || savingSort" data-test="menu-undo-sort" @click="undoSort">撤销</el-button>
          <span class="menu-view__side">
            <span v-if="sortDirty" class="menu-view__dirty" data-test="menu-sort-dirty">● 层级 / 排序有未保存变更</span>
            <el-button disabled title="导出能力本期未立项（置灰占位）" data-test="menu-export">导出</el-button>
            <span class="menu-view__hint">平台超管维护 · 租户只读</span>
          </span>
        </div>

        <div class="menu-view__filter">
          <el-input
            v-model="keyword"
            class="menu-view__kw"
            placeholder="关键字：菜单名称/路由路径"
            clearable
            data-test="menu-kw"
            @keyup.enter="search"
          />
          <el-select v-model="typeInput" class="menu-view__select" placeholder="菜单类型" clearable data-test="menu-type-filter">
            <el-option label="目录" value="directory" />
            <el-option label="菜单" value="menu" />
          </el-select>
          <el-select v-model="statusInput" class="menu-view__select" placeholder="状态" clearable data-test="menu-status-filter">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
          <el-button type="primary" data-test="menu-search" @click="search">查询</el-button>
          <el-button data-test="menu-reset" @click="resetFilter">重置</el-button>
          <span v-if="loading" class="menu-view__hint">载入中…</span>
        </div>

        <div class="menu-view__drag-tip">
          拖拽行首 <b>⋮⋮</b> 手柄调整：放到目标行手柄上＝<b>同级并排其后</b>；放到「菜单名称」＝<b>成为其子级</b>（仅目录可容纳下级）
        </div>

        <el-table
          ref="tableRef"
          :data="filteredTree"
          border
          row-key="id"
          :tree-props="{ children: 'children' }"
          :row-class-name="rowClassName"
          data-test="menu-table"
          @selection-change="(value: MenuItem[]) => (selection = value)"
          @row-dblclick="openRecord"
          @expand-change="onExpandChange"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column label="菜单名称" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <span
                class="menu-view__handle"
                draggable="true"
                title="拖拽调整层级 / 排序（放到目标行手柄＝同级并排其后）"
                data-test="menu-drag-handle"
                @dragstart="onDragStart($event, row)"
                @dragend="onDragEnd"
                @dragover.prevent="onDragOver(row, 'after')"
                @drop.prevent.stop="onDrop(row, 'after')"
              >
                ⋮⋮
              </span>
              <span
                class="menu-view__name"
                title="拖拽到此：成为该节点的子级（仅目录可容纳下级）"
                data-test="menu-drop-name"
                @dragover.prevent="onDragOver(row, 'inner')"
                @drop.prevent.stop="onDrop(row, 'inner')"
              >
                {{ row.name }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              <el-tag :type="menuTypeOf(row) === 'directory' ? 'info' : 'primary'" size="small">
                {{ menuTypeOf(row) === 'directory' ? '目录' : '菜单' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="path" label="路由路径" min-width="150" show-overflow-tooltip />
          <el-table-column label="视图组件" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.component ?? '—' }}</template>
          </el-table-column>
          <el-table-column prop="sort" label="排序" width="80" align="center" />
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
              title="暂无菜单"
              description="新增菜单后在此查看（双击行打开记录页签）。"
              :action="{ text: '去创建', type: 'primary' }"
              @action="openCreate"
            />
          </template>
        </el-table>

        <div class="menu-view__foot">
          <span class="menu-view__hint">树形元数据一次性返回，不分页；排序由拖拽调整，保存后回写 parent_id 与 sort</span>
        </div>
      </template>

      <template #record="{ tab }">
        <menu-record-tab
          v-if="tab"
          :key="tab.key"
          :menu-id="String(tab.key).replace('record:', '')"
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
.menu-view__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.menu-view__side {
  display: inline-flex;
  gap: var(--bms-space-3);
  align-items: center;
  margin-left: auto;
}

.menu-view__filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.menu-view__kw {
  width: 240px;
}

.menu-view__select {
  width: 140px;
}

.menu-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.menu-view__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.menu-view__drag-tip {
  margin-bottom: var(--bms-space-2);
  font-size: var(--bms-font-size-xs);
  color: var(--bms-color-text-secondary);
}

.menu-view__handle {
  display: inline-block;
  padding: 0 var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  letter-spacing: -2px;
  cursor: grab;
  user-select: none;
}

.menu-view__handle:hover {
  color: var(--bms-color-primary);
}

.menu-view__name {
  display: inline-block;
  width: calc(100% - 32px);
  vertical-align: middle;
}

.menu-view__foot {
  display: flex;
  justify-content: flex-start;
  margin-top: var(--bms-space-3);
}

:deep(.menu-view__row-after > td) {
  border-bottom: 2px solid var(--bms-color-primary);
}

:deep(.menu-view__row-into > td) {
  background: var(--bms-color-primary-light-9);
}
</style>
