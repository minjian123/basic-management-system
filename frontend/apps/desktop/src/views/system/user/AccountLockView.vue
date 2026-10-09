<script setup lang="ts">
// 账号锁定页（平台内建页）：表单框架宿主——列表 Tab + 账号锁定记录 Tab。
// 结构对照原型《08_用户管理/04_账号锁定.html》：列表**无操作列**、已解锁行不可选（不可重复解锁）；
// 工具栏「手动锁定」（`manual` 型：选用户 + 原因必填）与「解锁」（批量）。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { listAccountLocks, lockAccount, unlockAccount, type LockItem, type ManualLockRequest } from '@/api/accountLock'
import { listUsers, type UserItem } from '@/api/user'
import { useSessionStore } from '@/stores/session'
import { recordTabKey, useTabsStore } from '@/stores/tabs'

import AccountLockRecordTab from './AccountLockRecordTab.vue'
import { LOCK_TYPE_OPTIONS, UNLOCK_STATE_OPTIONS, formatDateTime, lockTypeLabel, lockTypeTag } from './labels'

defineOptions({ name: 'SystemAccountLock' })

/** 列表页签键（固定不可关）。 */
const LIST_KEY = 'list'
/** 每页条数（缺省 20）。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()
const session = useSessionStore()

/** 列表数据。 */
const rows = ref<LockItem[]>([])
/** 总数。 */
const total = ref(0)
/** 当前页。 */
const page = ref(1)
/** 关键字（用户名 / 姓名）。 */
const keyword = ref('')
/** 锁定类型筛选。 */
const lockType = ref('')
/** 解锁状态筛选（`open` / `done`）。 */
const unlockState = ref('')
/** 载入中。 */
const loading = ref(false)
/** 列表多选。 */
const selection = ref<LockItem[]>([])
/** 手动锁定弹窗可见。 */
const lockVisible = ref(false)
/** 手动锁定：候选用户。 */
const candidates = ref<UserItem[]>([])
/** 手动锁定：选中用户主键。 */
const lockUserId = ref('')
/** 手动锁定：原因。 */
const lockReason = ref('')

/** 权限判定。 */
const can = (code: string): boolean => session.codes.includes(code)
/** 表单框架页签。 */
const frameTabs = computed<FormFrameTab[]>(() =>
  tabs.tabs.map((tab) => ({ key: tab.key, title: tab.title, type: tab.type, closable: tab.closable, dirty: tab.dirty })),
)
/** 当前激活页签键。 */
const activeKey = computed(() => tabs.active)

/** 解锁状态筛选 → 后端 `active` 参数。 */
function activeParam(): boolean | undefined {
  if (unlockState.value === 'open') {
    return true
  }
  if (unlockState.value === 'done') {
    return false
  }
  return undefined
}

/** 载入锁定记录列表。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listAccountLocks({
      kw: keyword.value || undefined,
      lock_type: lockType.value || undefined,
      active: activeParam(),
      page: page.value,
      size: PAGE_SIZE,
    })
    rows.value = data.list ?? []
    total.value = data.total ?? 0
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '锁定记录加载失败')
  } finally {
    loading.value = false
  }
}

/** 检索。 */
function search(): void {
  page.value = 1
  void load()
}

/** 重置筛选。 */
function resetFilter(): void {
  keyword.value = ''
  lockType.value = ''
  unlockState.value = ''
  page.value = 1
  void load()
}

/** 已解锁行不可选（不可重复解锁）。 */
function rowSelectable(row: LockItem): boolean {
  return row.unlock_at === null
}

/**
 * 打开记录页签（双击行）。
 *
 * @param row 锁定记录行。
 */
function openRecord(row: LockItem): void {
  tabs.open(recordTabKey(String(row.id)), `${row.username || String(row.user_id)}`)
}

/** 打开手动锁定弹窗（载入候选用户）。 */
async function openLockDialog(): Promise<void> {
  lockUserId.value = ''
  lockReason.value = ''
  lockVisible.value = true
  try {
    const data = await listUsers({ status: 'enabled', size: 50 })
    candidates.value = data.list ?? []
  } catch {
    candidates.value = []
  }
}

/** 提交手动锁定。 */
async function submitLock(): Promise<void> {
  if (lockUserId.value === '') {
    ElMessage.error('请选择用户')
    return
  }
  if (lockReason.value.trim() === '') {
    ElMessage.error('请填写锁定原因')
    return
  }
  try {
    // 雪花主键按字符串提交（避免超出 JS 安全整数；后端宽松模式解析为 int）
    await lockAccount({ user_id: lockUserId.value, reason: lockReason.value } as unknown as ManualLockRequest)
    lockVisible.value = false
    ElMessage.success('已手动锁定（无期限，须手动解锁）')
    await load()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '锁定失败')
  }
}

/** 批量解锁（仅未解锁行）。 */
async function batchUnlock(): Promise<void> {
  const targets = selection.value.filter((row) => row.unlock_at === null)
  if (targets.length === 0) {
    ElMessage.error('请选择未解锁的锁定记录')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认解锁选中的 ${targets.length} 个账号？解锁记录将写入 sys_account_lock（unlock_by / unlock_at）并落操作日志与审计。`,
      '解锁确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  let done = 0
  for (const row of targets) {
    try {
      await unlockAccount(String(row.id))
      done += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : '解锁失败')
    }
  }
  if (done > 0) {
    ElMessage.success(`已解锁 ${done} 个账号`)
    selection.value = []
    await load()
  }
}

onMounted(() => {
  tabs.reset(LIST_KEY, '账号锁定')
  void load()
})
</script>

<template>
  <page-container title="账号锁定" description="锁定记录治理：手动锁定 / 手动解锁与解锁留痕">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text=""
      :before-close="tabs.close"
      data-test="account-lock-view"
      @update:model-value="tabs.activate"
      @close="tabs.close"
    >
      <template #list>
        <div class="lock-view__toolbar">
          <el-button v-if="can('user:lock')" type="primary" data-test="lock-manual" @click="openLockDialog">
            手动锁定
          </el-button>
          <el-button
            v-if="can('user:unlock')"
            :disabled="selection.length === 0"
            data-test="lock-batch-unlock"
            @click="batchUnlock"
          >
            解锁
          </el-button>
          <el-button data-test="lock-refresh" @click="load">刷新</el-button>
          <el-button data-test="lock-close-page" @click="tabs.reset(LIST_KEY, '账号锁定')">关闭</el-button>
          <span v-if="loading" class="lock-view__hint">载入中…</span>
        </div>

        <div class="lock-view__filter">
          <el-input
            v-model="keyword"
            class="lock-view__kw"
            placeholder="关键字：用户名 / 姓名"
            clearable
            data-test="lock-kw"
            @keyup.enter="search"
          />
          <el-select v-model="lockType" class="lock-view__select" placeholder="锁定类型" clearable data-test="lock-type">
            <el-option v-for="item in LOCK_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select
            v-model="unlockState"
            class="lock-view__select"
            placeholder="解锁状态"
            clearable
            data-test="lock-state"
          >
            <el-option v-for="item in UNLOCK_STATE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-button data-test="lock-search" @click="search">查询</el-button>
          <el-button data-test="lock-reset" @click="resetFilter">重置</el-button>
        </div>

        <el-table
          :data="rows"
          border
          row-key="id"
          data-test="lock-table"
          @selection-change="(value: LockItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" :selectable="rowSelectable" />
          <el-table-column prop="username" label="用户名" min-width="140" />
          <el-table-column prop="name" label="姓名" min-width="130" />
          <el-table-column label="锁定类型" width="150">
            <template #default="{ row }">
              <el-tag :type="lockTypeTag(row.lock_type)" effect="plain">{{ lockTypeLabel(row.lock_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="锁定时间" width="180">
            <template #default="{ row }">{{ formatDateTime(row.locked_at) }}</template>
          </el-table-column>
          <el-table-column label="自动解锁时间" min-width="180">
            <template #default="{ row }">
              {{ row.expire_at == null ? '—（须手动解锁）' : formatDateTime(row.expire_at) }}
            </template>
          </el-table-column>
          <el-table-column label="解锁状态" width="170">
            <template #default="{ row }">
              <el-tag v-if="row.unlock_at !== null" type="success" effect="plain">
                已解锁（{{ row.unlock_by ?? '系统' }}）
              </el-tag>
              <el-tag v-else type="danger" effect="plain">未解锁</el-tag>
            </template>
          </el-table-column>
          <template #empty>
            <empty-state type="data" title="暂无锁定记录" description="可「重置」筛选或使用「手动锁定」新增。" />
          </template>
        </el-table>

        <div class="lock-view__foot">
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
        <account-lock-record-tab
          v-if="tab"
          :key="tab.key"
          :lock-id="String(tab.key).replace('record:', '')"
          @close="tabs.discard(tab.key)"
        />
      </template>
    </form-frame>

    <el-dialog v-model="lockVisible" title="手动锁定账号" width="480" align-center data-test="lock-dialog">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="手动锁定为无期限锁定（manual 型），须手动解锁；锁定后该用户无法登录。"
      />
      <el-form label-position="top" class="lock-view__form">
        <el-form-item label="用户">
          <el-select v-model="lockUserId" filterable placeholder="选择用户" data-test="lock-dialog-user">
            <el-option
              v-for="item in candidates"
              :key="String(item.id)"
              :label="`${item.name ?? ''}（${item.username ?? ''}）`"
              :value="String(item.id)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="锁定原因">
          <el-input v-model="lockReason" type="textarea" :rows="3" placeholder="请填写锁定原因（写入锁定记录并落审计）" data-test="lock-dialog-reason" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-test="lock-dialog-cancel" @click="lockVisible = false">取消</el-button>
        <el-button type="danger" data-test="lock-dialog-confirm" @click="submitLock">确认锁定</el-button>
      </template>
    </el-dialog>
  </page-container>
</template>

<style scoped>
.lock-view__toolbar,
.lock-view__filter {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.lock-view__kw {
  width: 220px;
}

.lock-view__select {
  width: 170px;
}

.lock-view__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.lock-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}

.lock-view__form {
  margin-top: var(--bms-space-3);
}
</style>
