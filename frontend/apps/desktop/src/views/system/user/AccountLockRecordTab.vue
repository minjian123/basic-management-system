<script setup lang="ts">
// 账号锁定记录 Tab（表单框架的记录页）：锁定信息**只读** + 解锁（独立动作，不走表单编辑态）+ 解锁记录。
// 不含「修改密码」（重置密码入口收敛到用户记录页）。
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import { getAccountLock, unlockAccount, type LockItem } from '@/api/accountLock'
import { useSessionStore } from '@/stores/session'

import { formatDateTime, lockTypeLabel, lockTypeTag, unlockModeLabel } from './labels'

const props = defineProps<{
  /** 锁定记录主键。 */
  lockId: string
}>()

const emit = defineEmits<{ close: [] }>()

const session = useSessionStore()

/** 锁定记录。 */
const lock = ref<LockItem | null>(null)
/** 载入中。 */
const loading = ref(false)

/** 是否可解锁（权限码 + 未解锁）。 */
const canUnlock = computed(
  () => session.codes.includes('user:unlock') && lock.value !== null && lock.value.unlock_at === null,
)
/** 解锁记录（单条锁定记录自身的解锁留痕）。 */
const unlockLogs = computed<LockItem[]>(() => {
  const item = lock.value
  return item !== null && item.unlock_at !== null ? [item] : []
})

/** 载入锁定记录。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    lock.value = await getAccountLock(props.lockId)
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '锁定记录加载失败')
  } finally {
    loading.value = false
  }
}

/** 手动解锁（记录 `unlock_by` / `unlock_at`）。 */
async function unlock(): Promise<void> {
  const item = lock.value
  if (item === null) {
    return
  }
  try {
    await ElMessageBox.confirm(
      `手动解锁「${item.name}（${item.username}）」？解锁记录将写入 sys_account_lock（unlock_by / unlock_at）并落操作日志与审计。`,
      '解锁确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    lock.value = await unlockAccount(props.lockId)
    ElMessage.success('已解锁')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '解锁失败')
  }
}

watch(
  () => props.lockId,
  () => {
    void load()
  },
)

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="lock-record" data-test="account-lock-record">
    <div class="lock-record__bar">
      <el-button data-test="lock-record-refresh" @click="load">刷新</el-button>
      <el-button data-test="lock-record-close" @click="emit('close')">关闭</el-button>
      <span class="lock-record__side">
        <span v-if="loading" class="lock-record__hint" data-test="lock-record-loading">载入中…</span>
        <span class="lock-record__hint">锁定信息只读；解锁为独立操作（记录解锁人 / 解锁时间）</span>
      </span>
    </div>

    <div class="lock-record__section">账号锁定信息</div>
    <el-form label-position="top" disabled data-test="lock-record-form">
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="姓名"><el-input :model-value="lock?.name ?? '—'" /></el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="用户名"><el-input :model-value="lock?.username ?? '—'" /></el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="锁定类型">
            <el-tag :type="lockTypeTag(lock?.lock_type ?? '')" effect="plain">
              {{ lockTypeLabel(lock?.lock_type ?? '') }}
            </el-tag>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="锁定时间"><el-input :model-value="formatDateTime(lock?.locked_at)" /></el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="自动解锁时间">
            <el-input :model-value="lock?.expire_at == null ? '—（须手动解锁）' : formatDateTime(lock.expire_at)" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="锁定人">
            <el-input :model-value="lock?.locked_by == null ? '—（系统触发）' : String(lock.locked_by)" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item label="锁定原因"><el-input :model-value="lock?.reason ?? '—'" type="textarea" :rows="3" /></el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="lock-record__section">操作</div>
    <div class="lock-record__actions">
      <el-button v-if="canUnlock" type="primary" data-test="lock-record-unlock" @click="unlock">解锁</el-button>
      <el-alert
        v-if="lock !== null && lock.unlock_at !== null"
        type="success"
        :closable="false"
        show-icon
        :title="`账号已解锁（解锁人：${lock.unlock_by ?? '系统'}，${formatDateTime(lock.unlock_at)}，${unlockModeLabel(lock.unlock_mode)}）`"
      />
      <span v-else class="lock-record__hint">本锁定记录尚未解锁</span>
    </div>

    <div class="lock-record__section">解锁记录</div>
    <el-table :data="unlockLogs" size="small" border data-test="lock-record-logs">
      <el-table-column label="锁定时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.locked_at) }}</template>
      </el-table-column>
      <el-table-column label="锁定类型" width="140">
        <template #default="{ row }">{{ lockTypeLabel(row.lock_type) }}</template>
      </el-table-column>
      <el-table-column label="解锁人" width="140">
        <template #default="{ row }">{{ row.unlock_by ?? '系统' }}</template>
      </el-table-column>
      <el-table-column label="解锁时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.unlock_at) }}</template>
      </el-table-column>
      <el-table-column label="解锁方式" min-width="140">
        <template #default="{ row }">{{ unlockModeLabel(row.unlock_mode) }}</template>
      </el-table-column>
      <template #empty><span class="lock-record__hint">暂无解锁记录</span></template>
    </el-table>
  </div>
</template>

<style scoped>
.lock-record__bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.lock-record__side {
  margin-left: auto;
}

.lock-record__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.lock-record__section {
  margin: var(--bms-space-4) 0 var(--bms-space-2);
  padding-bottom: var(--bms-space-2);
  font-size: var(--bms-font-size-md);
  font-weight: 600;
  border-bottom: 1px solid var(--bms-color-border);
}

.lock-record__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
}
</style>
