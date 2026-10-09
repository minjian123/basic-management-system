<script setup lang="ts">
// 用户管理页（平台内建页）：表单框架宿主——列表 Tab（固定不可关）+ 用户记录 Tab（新增 / 双击行打开）。
// 结构对照原型《08_用户管理/02_用户列表页.html》：列表三段式**无操作列** + 状态列**内联开关**；
// 筛选仅「关键字 + 状态」（不含部门 / 岗位 / 角色——组织关系归 mdm，仅经记录页插件呈现）。
import { EmptyState, FormFrame, InlineSwitchCell, PageContainer, type FormFrameTab } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import {
  deleteUser,
  listUsers,
  resetUserPassword,
  updateUserStatus,
  type UserItem,
  type UserStatus,
} from '@/api/user'
import { recordTabKey, useTabsStore } from '@/stores/tabs'
import { useSessionStore } from '@/stores/session'

import UserRecordTab from './UserRecordTab.vue'
import { USER_STATUS_OPTIONS, userStatusLabel } from './labels'

defineOptions({ name: 'SystemUser' })

/** 列表页签键（固定不可关）。 */
const LIST_KEY = 'list'
/** 每页条数（缺省 20）。 */
const PAGE_SIZE = 20

const tabs = useTabsStore()
const session = useSessionStore()

/** 列表数据。 */
const rows = ref<UserItem[]>([])
/** 总数。 */
const total = ref(0)
/** 当前页。 */
const page = ref(1)
/** 关键字。 */
const keyword = ref('')
/** 状态筛选。 */
const status = ref('')
/** 载入中。 */
const loading = ref(false)
/** 列表多选。 */
const selection = ref<UserItem[]>([])
/** 重置密码弹窗。 */
const pwdVisible = ref(false)
/** 重置密码目标。 */
const pwdTarget = ref<UserItem | null>(null)
/** 新密码。 */
const pwdValue = ref('')
/** 强制首登改密。 */
const pwdForce = ref(true)

/** 权限判定。 */
const can = (code: string): boolean => session.codes.includes(code)
/** 表单框架页签。 */
const frameTabs = computed<FormFrameTab[]>(() =>
  tabs.tabs.map((tab) => ({ key: tab.key, title: tab.title, type: tab.type, closable: tab.closable, dirty: tab.dirty })),
)
/** 当前激活页签键。 */
const activeKey = computed(() => tabs.active)

/** 载入用户列表。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listUsers({
      kw: keyword.value || undefined,
      status: status.value || undefined,
      page: page.value,
      size: PAGE_SIZE,
    })
    rows.value = data.list ?? []
    total.value = data.total ?? 0
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '用户列表加载失败')
  } finally {
    loading.value = false
  }
}

/** 检索（回第一页）。 */
function search(): void {
  page.value = 1
  void load()
}

/**
 * 打开记录页签（双击行）。
 *
 * @param row 用户行。
 */
function openRecord(row: UserItem): void {
  tabs.open(recordTabKey(String(row.id)), `${row.name ?? ''}（${row.username ?? ''}）`)
}

/** 新增用户（记录页签新增态）。 */
function openCreate(): void {
  tabs.open(recordTabKey('new'), '新增用户')
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
 * 状态内联切换（停用为危险操作：二次确认，失败抛错由件回滚显示）。
 *
 * @param row 用户行。
 * @param next 目标状态（真＝启用）。
 * @returns 保存 promise（抛错即回滚）。
 */
async function toggleStatus(row: UserItem, next: boolean): Promise<void> {
  const target: UserStatus = next ? 'enabled' : 'disabled'
  if (target === 'disabled') {
    await ElMessageBox.confirm(
      `停用「${row.name ?? ''}」将立即失效该用户全部会话（踢出），确认停用？`,
      '停用确认',
      { type: 'warning' },
    ).catch(() => {
      throw new Error('已取消')
    })
  }
  await updateUserStatus(String(row.id), target)
  row.status = target
  ElMessage.success(`已${userStatusLabel(target)}`)
}

/** 批量删除。 */
async function removeSelected(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 个用户？`, '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let removed = 0
  for (const row of selection.value) {
    try {
      await deleteUser(String(row.id))
      removed += 1
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : `删除失败：${row.username ?? ''}`)
    }
  }
  if (removed > 0) {
    ElMessage.success(`已删除 ${removed} 个用户`)
    selection.value = []
    await load()
  }
}

/** 批量启用 / 停用。 */
async function batchToggle(): Promise<void> {
  if (selection.value.length === 0) {
    return
  }
  const toDisabled = selection.value.some((row) => row.status === 'enabled')
  const target: UserStatus = toDisabled ? 'disabled' : 'enabled'
  try {
    await ElMessageBox.confirm(
      `确认${userStatusLabel(target)}选中的 ${selection.value.length} 个用户？停用将即时失效其全部会话。`,
      '批量操作确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  for (const row of selection.value) {
    try {
      await updateUserStatus(String(row.id), target)
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : '操作失败')
    }
  }
  ElMessage.success(`已批量${userStatusLabel(target)}`)
  selection.value = []
  await load()
}

/** 打开重置密码弹窗（限单行选中）。 */
function openResetPassword(): void {
  if (selection.value.length !== 1) {
    ElMessage.error('请选择一行（重置密码不支持批量）')
    return
  }
  pwdTarget.value = selection.value[0] ?? null
  pwdValue.value = ''
  pwdForce.value = true
  pwdVisible.value = true
}

/** 确认重置密码。 */
async function doResetPassword(): Promise<void> {
  const target = pwdTarget.value
  if (target === null) {
    return
  }
  if (pwdValue.value.trim() === '') {
    ElMessage.error('请输入新密码')
    return
  }
  try {
    await resetUserPassword(String(target.id), { new_password: pwdValue.value, force_change: pwdForce.value })
    pwdVisible.value = false
    ElMessage.success('密码已重置（全部会话已失效）')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '重置失败')
  }
}

/**
 * 记录保存成功回调（刷新列表并同步页签标题）。
 *
 * @param user 保存后的用户详情。
 */
function onSaved(user: { id?: string; name?: string; username?: string }): void {
  const key = recordTabKey(String(user.id ?? ''))
  const tab = tabs.tabOf(key)
  if (tab !== undefined) {
    tab.title = `${user.name ?? ''}（${user.username ?? ''}）`
  }
  tabs.activate(key)
  void load()
}

/**
 * 记录页签脏态同步。
 *
 * @param key 页签键。
 * @param dirty 是否脏。
 */
function onRecordDirty(key: string, dirty: boolean): void {
  tabs.setDirty(key, dirty)
}

onMounted(() => {
  tabs.reset(LIST_KEY, '用户管理')
  void load()
})
</script>

<template>
  <page-container title="用户管理" description="用户＝系统账号：账号生命周期治理；组织关系归 mdm，仅经记录页插件呈现">
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="新增"
      :before-close="closeTab"
      data-test="user-view"
      @update:model-value="tabs.activate"
      @open="openCreate"
      @close="tabs.close"
    >
      <template #list>
        <div class="user-view__toolbar">
          <el-button v-if="can('user:create')" type="primary" data-test="user-create" @click="openCreate">新增</el-button>
          <el-button data-test="user-refresh" @click="load">刷新</el-button>
          <el-button data-test="user-close-page" @click="tabs.reset(LIST_KEY, '用户管理')">关闭</el-button>
          <el-button
            v-if="can('user:delete')"
            type="danger"
            plain
            :disabled="selection.length === 0"
            data-test="user-batch-delete"
            @click="removeSelected"
          >
            删除
          </el-button>
          <el-button :disabled="selection.length === 0" data-test="user-batch-toggle" @click="batchToggle">
            启用/停用
          </el-button>
          <el-button
            v-if="can('user:reset_pwd')"
            :disabled="selection.length !== 1"
            data-test="user-reset-pwd"
            @click="openResetPassword"
          >
            重置密码
          </el-button>
        </div>

        <div class="user-view__filter">
          <el-input
            v-model="keyword"
            class="user-view__kw"
            placeholder="关键字：用户名/姓名/手机号/邮箱"
            clearable
            data-test="user-kw"
            @keyup.enter="search"
          />
          <el-select v-model="status" class="user-view__status" placeholder="全部" clearable data-test="user-status">
            <el-option v-for="item in USER_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-button data-test="user-search" @click="search">查询</el-button>
          <span v-if="loading" class="user-view__hint">载入中…</span>
        </div>

        <el-table
          :data="rows"
          border
          row-key="id"
          data-test="user-table"
          @selection-change="(value: UserItem[]) => (selection = value)"
          @row-dblclick="openRecord"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column prop="username" label="用户名" min-width="140" />
          <el-table-column prop="name" label="姓名" min-width="150" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <inline-switch-cell
                :model-value="row.status === 'enabled'"
                :save="(next: boolean) => toggleStatus(row as UserItem, next)"
                :data-test="`user-status-switch-${row.id}`"
              />
            </template>
          </el-table-column>
          <el-table-column prop="last_login_at" label="最近登录" min-width="180" />
          <template #empty>
            <empty-state
              type="data"
              title="暂无用户"
              description="点击「新增」创建用户（双击行打开记录页签）。"
            />
          </template>
        </el-table>

        <div class="user-view__foot">
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
        <user-record-tab
          v-if="tab"
          :key="tab.key"
          :user-id="String(tab.key).replace('record:', '')"
          @saved="onSaved"
          @dirty="(value: boolean) => onRecordDirty(tab.key, value)"
          @close="tabs.discard(tab.key)"
        />
      </template>
    </form-frame>

    <el-dialog v-model="pwdVisible" title="重置密码" width="480" align-center data-test="user-pwd-dialog">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="重置后原密码失效，用户所有会话将退出（会话即时失效）。"
      />
      <el-form label-position="top" class="user-view__pwd-form">
        <el-form-item label="新密码">
          <el-input v-model="pwdValue" type="password" show-password placeholder="8-32 位，含字母数字" data-test="user-pwd-input" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="pwdForce" data-test="user-pwd-force">强制下次登录改密</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-test="user-pwd-cancel" @click="pwdVisible = false">取消</el-button>
        <el-button type="danger" data-test="user-pwd-confirm" @click="doResetPassword">确认重置</el-button>
      </template>
    </el-dialog>
  </page-container>
</template>

<style scoped>
.user-view__toolbar {
  display: flex;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.user-view__filter {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.user-view__kw {
  width: 220px;
}

.user-view__status {
  width: 140px;
}

.user-view__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.user-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}

.user-view__pwd-form {
  margin-top: var(--bms-space-3);
}
</style>
