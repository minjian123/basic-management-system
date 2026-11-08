<script setup lang="ts">
// 租户管理页（平台超管）：列表 Tab（固定不可关）+ 记录 Tab（双击行打开）。
// 列表三段式无操作列之外提供「开通 / 停用 / 启用 / 注销 / 恢复」动作；开通弹窗展示一次性初始口令；
// 注销须手动输入租户编码二次确认（后端亦强校验），已注销行展示清理时点或「待归档」。
import { EmptyState, FormFrame, PageContainer, type FormFrameTab } from '@bms/ui_ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '@/api/error'
import {
  activateTenant,
  createTenant,
  deleteTenant,
  fetchModuleOptions,
  listTenants,
  restoreTenant,
  suspendTenant,
  type TenantCreateRequest,
  type TenantItem,
  type TenantModuleOption,
} from '@/api/tenantAdmin'
import { recordTabKey, useTabsStore } from '@/stores/tabs'

import TenantRecordTab from './TenantRecordTab.vue'
import { TENANT_STATUS_OPTIONS, tenantStatusLabel, tenantStatusTag } from './tenant/labels'

defineOptions({ name: 'SystemTenant' })

/** 列表页签键（固定不可关）。 */
const LIST_KEY = 'list'
/** 每页条数。 */
const PAGE_SIZE = 20

/** 注销确认码不匹配（`82014`）。 */
const ERR_DELETE_CONFIRM_MISMATCH = 82014
/** 当前状态不允许该操作（`82003`）。 */
const ERR_STATE_CONFLICT = 82003
/** 保留期已过、不可恢复（`82015`）。 */
const ERR_RETENTION_CLOSED = 82015

const tabs = useTabsStore()

/** 列表数据。 */
const rows = ref<TenantItem[]>([])
/** 总数。 */
const total = ref(0)
/** 当前页。 */
const page = ref(1)
/** 编码筛选。 */
const codeFilter = ref('')
/** 名称筛选。 */
const nameFilter = ref('')
/** 状态筛选。 */
const statusFilter = ref('')
/** 载入中。 */
const loading = ref(false)
/** 开通弹窗可见。 */
const provisionVisible = ref(false)
/** 开通提交中。 */
const provisioning = ref(false)
/** 模块选项（开通弹窗）。 */
const moduleOptions = ref<TenantModuleOption[]>([])
/** 注销弹窗可见。 */
const deleteVisible = ref(false)
/** 注销目标行（关闭弹窗后保留，避免关闭动画期间内容跳空）。 */
const deleteTarget = ref<TenantItem | null>(null)
/** 注销确认码（须与租户编码完全一致）。 */
const deleteConfirmCode = ref('')
/** 注销原因（选填）。 */
const deleteReason = ref('')
/** 注销提交中。 */
const deleting = ref(false)
/** 开通表单。 */
const provisionForm = ref<{
  code: string
  name: string
  domain: string
  modules: string[]
}>({ code: '', name: '', domain: '', modules: [] })

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

/** 可勾选模块（目录已启用且为产品模块）。 */
const optionalModules = computed(() => moduleOptions.value.filter((item) => item.optional))

/** 注销提交可用（确认码与目标租户编码完全一致，不做大小写宽松匹配）。 */
const canDelete = computed(() => deleteTarget.value !== null && deleteConfirmCode.value === deleteTarget.value.code)

/**
 * 载入租户列表。
 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listTenants({
      code: codeFilter.value || undefined,
      name: nameFilter.value || undefined,
      status: statusFilter.value || undefined,
      page: page.value,
      size: PAGE_SIZE,
    })
    rows.value = data.list ?? []
    total.value = data.total ?? 0
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '租户列表加载失败')
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
 * 清理时点文本（仅已注销行有值；`purge_at` 为空表示尚未进入清理倒计时）。
 *
 * @param row 租户行。
 * @returns 清理日期 `YYYY-MM-DD`；非已注销行或待归档返回 `undefined`。
 */
function purgeDate(row: TenantItem): string | undefined {
  if (row.status !== 'deleted' || !row.purge_at) {
    return undefined
  }
  return String(row.purge_at).slice(0, 10)
}

/**
 * 是否已过保留期（过期不可恢复；时点非法按未过期处理，交后端兜底）。
 *
 * @param row 租户行。
 */
function isPurgeExpired(row: TenantItem): boolean {
  return row.status === 'deleted' && row.purge_at != null && Date.parse(String(row.purge_at)) <= Date.now()
}

/**
 * 动作失败文案（按后端错误码区分原因，避免三种拒绝混成一句笼统提示）。
 *
 * @param error 捕获的异常。
 * @param fallback 无可用信息时的兜底文案。
 */
function actionErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code === ERR_DELETE_CONFIRM_MISMATCH) {
      return '确认码与租户编码不一致'
    }
    if (error.code === ERR_STATE_CONFLICT) {
      return '当前租户状态不允许该操作'
    }
    if (error.code === ERR_RETENTION_CLOSED) {
      return '已过保留期，需运维介入处理'
    }
    return error.message
  }
  return error instanceof Error ? error.message : fallback
}

/**
 * 打开记录页签（双击行）。
 *
 * @param row 租户行。
 */
function openRecord(row: TenantItem): void {
  tabs.open(recordTabKey(String(row.id)), `${row.name ?? ''}（${row.code ?? ''}）`)
}

/** 打开开通弹窗并加载模块选项。 */
async function openProvision(): Promise<void> {
  provisionForm.value = { code: '', name: '', domain: '', modules: [] }
  provisionVisible.value = true
  try {
    const result = await fetchModuleOptions()
    moduleOptions.value = result.items ?? []
  } catch (error: unknown) {
    moduleOptions.value = []
    ElMessage.error(error instanceof Error ? error.message : '模块选项加载失败')
  }
}

/** 提交开通（成功展示一次性初始口令）。 */
async function submitProvision(): Promise<void> {
  if (provisionForm.value.code.trim() === '' || provisionForm.value.name.trim() === '') {
    ElMessage.warning('请填写租户编码与名称')
    return
  }
  provisioning.value = true
  try {
    const body: TenantCreateRequest = {
      code: provisionForm.value.code.trim().toLowerCase(),
      name: provisionForm.value.name.trim(),
      domain: provisionForm.value.domain.trim() || null,
      modules: [...provisionForm.value.modules],
    }
    const result = await createTenant(body)
    provisionVisible.value = false
    await load()
    await ElMessageBox.alert(
      `初始管理员账号：${result.admin_username}\n初始口令：${result.initial_password}\n口令仅本次显示，首次登录将强制修改。`,
      '租户开通成功',
      { type: 'success', confirmButtonText: '我已记录' },
    )
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '租户开通失败')
  } finally {
    provisioning.value = false
  }
}

/**
 * 停用 / 启用租户。
 *
 * @param row 租户行。
 */
async function toggleStatus(row: TenantItem): Promise<void> {
  const suspend = row.status === 'active'
  try {
    await ElMessageBox.confirm(
      suspend ? `确认停用租户「${row.name}」？停用后将撤销该租户全部在线会话。` : `确认启用租户「${row.name}」？`,
      suspend ? '停用租户' : '启用租户',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    if (suspend) {
      await suspendTenant(String(row.id))
    } else {
      await activateTenant(String(row.id))
    }
    ElMessage.success(suspend ? '租户已停用' : '租户已启用')
    await load()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '状态切换失败')
  }
}

/**
 * 打开注销确认弹窗（清空上次输入）。
 *
 * @param row 租户行。
 */
function openDelete(row: TenantItem): void {
  deleteTarget.value = row
  deleteConfirmCode.value = ''
  deleteReason.value = ''
  deleteVisible.value = true
}

/**
 * 提交注销（确认码须与租户编码完全一致；原因选填）。
 */
async function submitDelete(): Promise<void> {
  const target = deleteTarget.value
  if (target === null) {
    return
  }
  if (deleteConfirmCode.value !== target.code) {
    // 弹窗按钮已禁用，这里只兜「回车 / 程序化触发」；后端亦强校验，前端不作为唯一防线
    ElMessage.warning('请输入完整租户编码以确认')
    return
  }
  deleting.value = true
  try {
    const detail = await deleteTenant(String(target.id), {
      confirm_code: deleteConfirmCode.value,
      reason: deleteReason.value.trim() || null,
    })
    deleteVisible.value = false
    const until = detail.purge_at ? String(detail.purge_at).slice(0, 10) : ''
    ElMessage.success(until ? `租户已注销，保留期至 ${until}` : '租户已注销，归档就绪后进入清理倒计时')
    await load()
  } catch (error: unknown) {
    ElMessage.error(actionErrorMessage(error, '租户注销失败'))
  } finally {
    deleting.value = false
  }
}

/**
 * 恢复已注销租户（保留期内；过期由后端拒绝）。
 *
 * @param row 租户行。
 */
async function restore(row: TenantItem): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认恢复租户「${row.name}」？恢复后立即可用，保留期倒计时取消。`, '恢复租户', {
      type: 'warning',
      confirmButtonText: '恢复',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await restoreTenant(String(row.id))
    ElMessage.success('租户已恢复')
    await load()
  } catch (error: unknown) {
    ElMessage.error(actionErrorMessage(error, '租户恢复失败'))
  }
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
 * 记录保存成功回调（刷新列表并同步标题）。
 *
 * @param tenant 保存后的租户详情。
 */
function onSaved(tenant: { id?: string; name?: string; code?: string }): void {
  const key = recordTabKey(String(tenant.id ?? ''))
  const tab = tabs.tabOf(key)
  if (tab !== undefined) {
    tab.title = `${tenant.name ?? ''}（${tenant.code ?? ''}）`
  }
  tabs.activate(key)
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
  tabs.reset(LIST_KEY, '租户管理')
  void load()
})
</script>

<template>
  <page-container
    title="租户管理"
    description="平台租户与业务租户：开通 / 停用启用 / 域名 / 配额 / 模块开关（仅平台超管可见）"
  >
    <form-frame
      :model-value="activeKey"
      :tabs="frameTabs"
      open-text="开通租户"
      :before-close="closeTab"
      data-test="tenant-view"
      @update:model-value="tabs.activate"
      @open="openProvision"
      @close="tabs.close"
    >
      <template #list>
        <div class="tenant-view__toolbar">
          <el-button type="primary" data-test="tenant-create" @click="openProvision">开通租户</el-button>
        </div>

        <div class="tenant-view__filter">
          <el-input
            v-model="codeFilter"
            class="tenant-view__kw"
            placeholder="租户编码"
            clearable
            data-test="tenant-code-filter"
            @keyup.enter="search"
          />
          <el-input
            v-model="nameFilter"
            class="tenant-view__kw"
            placeholder="租户名称"
            clearable
            data-test="tenant-name-filter"
            @keyup.enter="search"
          />
          <el-select
            v-model="statusFilter"
            class="tenant-view__status"
            placeholder="状态"
            clearable
            data-test="tenant-status-filter"
          >
            <el-option
              v-for="item in TENANT_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <el-button data-test="tenant-search" @click="search">查询</el-button>
          <span v-if="loading" class="tenant-view__hint">载入中…</span>
        </div>

        <el-table :data="rows" border row-key="id" data-test="tenant-table" @row-dblclick="openRecord">
          <el-table-column prop="code" label="租户编码" min-width="140" />
          <el-table-column prop="name" label="租户名称" min-width="160" />
          <el-table-column prop="domain" label="子域名" min-width="180">
            <template #default="{ row }">
              <span>{{ row.domain || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="tenantStatusTag(row.status)" size="small" data-test="tenant-status-tag">
                {{ tenantStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="已开通模块" min-width="180">
            <template #default="{ row }">
              <span data-test="tenant-modules">{{ (row.modules ?? []).join('、') || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="到期时间" min-width="170">
            <template #default="{ row }">
              <span>{{ row.expire_at ? String(row.expire_at).replace('T', ' ').slice(0, 19) : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="清理时点" min-width="130">
            <template #default="{ row }">
              <span v-if="purgeDate(row)" data-test="tenant-purge-at">{{ purgeDate(row) }}</span>
              <span v-else-if="row.status === 'deleted'" class="tenant-view__muted" data-test="tenant-purge-pending">
                待归档
              </span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'active' || row.status === 'suspended'">
                <el-button
                  link
                  :type="row.status === 'active' ? 'danger' : 'primary'"
                  data-test="tenant-toggle"
                  @click="toggleStatus(row)"
                >
                  {{ row.status === 'active' ? '停用' : '启用' }}
                </el-button>
                <el-button link type="danger" data-test="tenant-delete" @click="openDelete(row)"> 注销 </el-button>
              </template>
              <template v-else-if="row.status === 'deleted'">
                <el-button
                  v-if="!isPurgeExpired(row)"
                  link
                  type="primary"
                  data-test="tenant-restore"
                  @click="restore(row)"
                >
                  恢复
                </el-button>
                <span v-else class="tenant-view__muted" data-test="tenant-expired">已过保留期</span>
              </template>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <template #empty>
            <empty-state
              type="data"
              title="暂无租户"
              description="点击「开通租户」创建业务租户后在此查看（双击行打开记录页签）。"
            />
          </template>
        </el-table>

        <div class="tenant-view__foot">
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
        <tenant-record-tab
          v-if="tab"
          :key="tab.key"
          :tenant-id="String(tab.key).replace('record:', '')"
          @saved="onSaved"
          @dirty="(value: boolean) => onRecordDirty(tab.key, value)"
          @close="tabs.discard(tab.key)"
        />
      </template>
    </form-frame>

    <el-dialog v-model="provisionVisible" title="开通租户" width="560px" data-test="tenant-provision-dialog">
      <el-form label-width="96px">
        <el-form-item label="租户编码" required>
          <el-input
            v-model="provisionForm.code"
            placeholder="全小写字母 / 数字 / 连字符"
            data-test="tenant-provision-code"
          />
        </el-form-item>
        <el-form-item label="租户名称" required>
          <el-input v-model="provisionForm.name" data-test="tenant-provision-name" />
        </el-form-item>
        <el-form-item label="子域名">
          <el-input
            v-model="provisionForm.domain"
            placeholder="如 acme.bms.example.com"
            data-test="tenant-provision-domain"
          />
        </el-form-item>
        <el-form-item label="开通模块">
          <el-checkbox-group v-model="provisionForm.modules" data-test="tenant-provision-modules">
            <el-checkbox v-for="item in optionalModules" :key="item.module_key" :value="item.module_key">
              {{ item.name }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="provisionVisible = false">取消</el-button>
        <el-button type="primary" :loading="provisioning" data-test="tenant-provision-submit" @click="submitProvision">
          开通
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteVisible"
      title="注销租户"
      width="520px"
      :close-on-click-modal="false"
      data-test="tenant-delete-dialog"
    >
      <el-alert type="warning" :closable="false" show-icon class="tenant-view__alert">
        <template #title>注销后该租户立即不可用（在线会话被撤销）</template>
        <div>保留期内可恢复；保留期到期后数据将被物理清理且不可恢复。</div>
      </el-alert>
      <el-form label-position="top">
        <el-form-item label="确认租户编码" required>
          <el-input
            v-model="deleteConfirmCode"
            :placeholder="`请输入 ${deleteTarget ? deleteTarget.code : ''} 以确认`"
            data-test="tenant-delete-confirm"
          />
          <span class="tenant-view__muted">须与租户编码完全一致（区分大小写），不匹配无法提交。</span>
        </el-form-item>
        <el-form-item label="注销原因（选填，≤200 字）">
          <el-input
            v-model="deleteReason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="如：客户终止合作 / 重复开通"
            data-test="tenant-delete-reason"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deleteVisible = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="!canDelete"
          :loading="deleting"
          data-test="tenant-delete-submit"
          @click="submitDelete"
        >
          确认注销
        </el-button>
      </template>
    </el-dialog>
  </page-container>
</template>

<style scoped>
.tenant-view__toolbar {
  display: flex;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.tenant-view__filter {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.tenant-view__kw {
  width: 180px;
}

.tenant-view__status {
  width: 140px;
}

.tenant-view__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.tenant-view__muted {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.tenant-view__alert {
  margin-bottom: var(--bms-space-3);
}

.tenant-view__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bms-space-3);
}
</style>
