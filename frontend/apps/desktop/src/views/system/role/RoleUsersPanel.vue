<script setup lang="ts">
// 平台内建区域项「用户分配」（挂 `sys.role.detail.assign`，与 mdm 岗位 / 部门插件同槽并列）。
//
// 角色记录页「角色分配」页签内的第一个子页签；改动**只进草稿**，由宿主工具栏「保存」经
// 角色保存编排端点（`PUT /roles/{id}/assignments`）与本体一次原子提交（见 `02_03/_02` 详设）。
// 无宿主通道（如独立运行）时**只读**，避免绕过编排直写关系表。
import { EmptyState, useModuleSlotField, type HostSubmitterRegistrar } from '@bms/ui-ep'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import { listRoleUsers, type AssignedUserItem } from '@/api/role'
import { listUsers, type UserItem } from '@/api/user'
import { useSessionStore } from '@/stores/session'

/** 本区域项承担的分段名（与编排端点 `user_ids` 字段对应）。 */
const SEGMENT_KEY = 'user_ids'
/** 单页拉取条数（全量基线合并用）。 */
const PAGE_SIZE = 200

const session = useSessionStore()

/** 作用实体标识（宿主记录页显式注入）。 */
const roleId = useModuleSlotField<string>('roleId')
/** 宿主提交器注册通道（值即函数；缺失 ⇒ 只读）。 */
const registrar = useModuleSlotField<HostSubmitterRegistrar>('registerSubmitter')

/** 已分配（服务端口径，全量集合）。 */
const assigned = ref<AssignedUserItem[]>([])
/** 草稿勾选集合。 */
const picked = ref<string[]>([])
/** 候选用户。 */
const candidates = ref<UserItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 弹窗可见。 */
const pickerVisible = ref(false)
/** 弹窗关键字。 */
const keyword = ref('')

/** 是否可写（需宿主通道与 `role:grant` 权限码）。 */
const writable = computed(() => registrar.value !== undefined && session.codes.includes('role:grant'))
/** 是否存在未提交改动（集合差异）。 */
const dirty = computed(() => {
  const saved = assigned.value.map((item) => String(item.user_id))
  return saved.length !== picked.value.length || saved.some((id) => !picked.value.includes(id))
})

/**
 * 载入该角色**全部**已分配用户（分页合并，作为全量覆盖基线；上下文缺失即短路）。
 */
async function load(): Promise<void> {
  const id = roleId.value
  if (id === undefined || id === '') {
    return
  }
  loading.value = true
  try {
    const rows: AssignedUserItem[] = []
    let page = 1
    for (;;) {
      const data = await listRoleUsers(id, { page, size: PAGE_SIZE })
      const batch = data.list ?? []
      rows.push(...batch)
      const total = data.total ?? rows.length
      if (batch.length === 0 || rows.length >= total) {
        break
      }
      page += 1
    }
    assigned.value = rows
    picked.value = rows.map((item) => String(item.user_id))
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '已分配用户加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 载入候选用户（仅启用账号）。
 */
async function loadCandidates(): Promise<void> {
  try {
    const data = await listUsers({ kw: keyword.value || undefined, status: 'enabled', size: 50 })
    candidates.value = data.list ?? []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '用户列表加载失败')
  }
}

/** 打开选择用户弹窗。 */
function openPicker(): void {
  keyword.value = ''
  pickerVisible.value = true
  void loadCandidates()
}

/** 弹窗内勾选变化（只改草稿）。 */
function onPickChange(ids: (string | number | boolean)[]): void {
  picked.value = ids.map((id) => String(id))
}

/** 关闭弹窗（草稿保留）。 */
function closePicker(): void {
  pickerVisible.value = false
}

/** 弹窗候选（按账号 / 姓名过滤）。 */
const filteredCandidates = computed<UserItem[]>(() => {
  const key = keyword.value.trim().toLowerCase()
  if (key === '') {
    return candidates.value
  }
  return candidates.value.filter((item) => `${item.username ?? ''}${item.name ?? ''}`.toLowerCase().includes(key))
})

// 宿主收草稿：登记提交器（无改动返回 null）
watch(
  registrar,
  (target) => {
    target?.({
      isDirty: () => dirty.value,
      buildSegment: () => (dirty.value ? { key: SEGMENT_KEY, value: { user_ids: [...picked.value] } } : null),
      reload: load,
    })
  },
  { immediate: true },
)

watch(roleId, () => {
  void load()
})

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="role-users-assign" data-test="role-users-assign">
    <empty-state
      v-if="roleId === undefined || roleId === ''"
      type="data"
      title="尚未选择角色"
      description="角色创建 / 打开记录后可分配用户。"
      data-test="role-users-context-absent"
    />

    <template v-else>
      <div class="role-users-assign__bar">
        <el-button v-if="writable" type="primary" size="small" data-test="role-users-open" @click="openPicker">
          选择用户
        </el-button>
        <span class="role-users-assign__hint">
          与用户管理页「用户分配 — 角色分配」同一张关系表（`sys_user_role`）；改动随工具栏「保存」提交
        </span>
        <span class="role-users-assign__count" data-test="role-users-count">已分配 {{ picked.length }}</span>
      </div>

      <p v-if="!writable" class="role-users-assign__hint" data-test="role-users-readonly">
        只读：需具备 `role:grant` 权限码且在记录页内打开。
      </p>
      <p v-if="loading" class="role-users-assign__hint" data-test="role-users-loading">载入中…</p>
      <p v-if="dirty" class="role-users-assign__dirty" data-test="role-users-dirty">● 有未保存的用户分配变更</p>

      <el-table :data="assigned" border size="small" data-test="role-users-table">
        <el-table-column prop="username" label="账号" min-width="140" />
        <el-table-column prop="name" label="姓名" min-width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
              {{ row.status === 'enabled' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <template #empty>
          <empty-state type="data" title="暂未分配用户" description="点击「选择用户」后随工具栏「保存」生效。" />
        </template>
      </el-table>

      <el-dialog v-model="pickerVisible" title="选择用户" width="560" align-center>
        <div class="role-users-assign__picker">
          <el-input
            v-model="keyword"
            placeholder="账号 / 姓名"
            clearable
            data-test="role-users-picker-kw"
            @keyup.enter="loadCandidates"
          />
          <el-button data-test="role-users-picker-search" @click="loadCandidates">查询</el-button>
        </div>
        <el-checkbox-group
          :model-value="picked"
          class="role-users-assign__candidates"
          data-test="role-users-picker"
          @change="onPickChange"
        >
          <el-checkbox
            v-for="item in filteredCandidates"
            :key="String(item.id)"
            :value="String(item.id)"
            :data-test="`role-users-candidate-${item.id}`"
          >
            {{ item.name }}（{{ item.username }}）
          </el-checkbox>
        </el-checkbox-group>
        <template #footer>
          <el-button data-test="role-users-picker-cancel" @click="closePicker">取消</el-button>
          <el-button type="primary" data-test="role-users-picker-confirm" @click="closePicker">确定</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
.role-users-assign__bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-2);
}

.role-users-assign__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.role-users-assign__count {
  margin-left: auto;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.role-users-assign__dirty {
  margin: 0 0 var(--bms-space-2);
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-sm);
}

.role-users-assign__picker {
  display: flex;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.role-users-assign__candidates {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  overflow: auto;
}
</style>
